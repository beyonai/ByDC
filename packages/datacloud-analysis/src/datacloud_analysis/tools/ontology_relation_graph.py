"""OntologyRelationGraph — 本体关系图驱动器。

从 OntologyLoader 的 get_ontology_relations() 构建关系图，
驱动 after_hook 的工具解锁逻辑。

设计原则：
  - 不查数据库，从 OntologyLoader 内存数据构建，零额外 IO
  - 只关注 ops_* 对象之间的关系，且必须有 resolve_action_code
  - get_next_objects() 无条件返回所有关联目标工具（框架不做条件过滤）
  - description JSON 里的 unlock_reason / unlock_hint 只给 LLM 看，不影响解锁逻辑
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NextObjectSuggestion:
    """工具执行完后推荐跳转到的下一个对象和工具。"""

    object_code: str  # 目标对象编码，如 "ops_early_span"
    tool: str  # 目标工具名 = OntologyRelation.resolve_action_code
    reason: str  # 解锁原因（给 LLM 看，注入 dynamic_prompt）
    hint: str = ""  # 参数填写提示（给 LLM 看）
    relation_type: str = ""  # CONTAINS / DERIVES_FROM / VALIDATES / DIAGNOSE


class OntologyRelationGraph:
    """从 OntologyLoader.get_ontology_relations() 构建的本体关系图。

    驱动 HookAwareToolNode after_hook 的工具解锁：工具执行完后，
    查以该对象为 source 的所有关系，把全部 resolve_action_code 无条件加入 active_tools。

    是否实际调用某个解锁工具，由 LLM 根据 unlock_reason 自主判断，框架不做条件过滤。
    """

    def __init__(self, loader: Any) -> None:
        """从 OntologyLoader 实例构建关系图。

        Args:
            loader: 已 load 好的 OntologyLoader（与 TOOL_POOL 初始化共用同一实例）。
        """
        self._relations: list[dict[str, Any]] = []
        self._load_from_loader(loader)

    def _load_from_loader(self, loader: Any) -> None:
        """从 loader.get_ontology_relations() 读取关系数据。"""
        try:
            relations = loader.get_ontology_relations()
        except Exception:  # noqa: BLE001
            logger.warning("OntologyRelationGraph: get_ontology_relations() failed", exc_info=True)
            return

        for rel in relations:
            # 只处理 ops_* 对象的关系
            source = getattr(rel, "source_class", "") or ""
            if not source.startswith("ops_"):
                continue

            # resolve_action_code 的读取策略（按优先级）：
            # 1. OntologyRelation.resolve_action_code（SDK models.py 有此字段，但 _parse_term_relation 不填它）
            # 2. relation_name（parser 会读此字段，OWL 里把 resolve_action_code 写入 relation_name）
            # 3. description JSON 里的 resolve_action_code（兜底）
            resolve_action = getattr(rel, "resolve_action_code", None) or ""
            if not resolve_action:
                # parser 把 relation_name 读进来，OWL 文件里 relation_name = action_code
                resolve_action = getattr(rel, "relation_name", "") or ""
            if not resolve_action:
                # 兜底：从 description JSON 里读
                desc_raw = getattr(rel, "description", "") or ""
                if desc_raw:
                    from contextlib import suppress
                    with suppress(json.JSONDecodeError, TypeError, ValueError):
                        resolve_action = json.loads(desc_raw).get("resolve_action_code", "") or ""
            if not resolve_action:
                continue  # 仍然没有 resolve_action_code，跳过

            # 解析 description 里的 unlock_reason / unlock_hint（给 LLM 看）
            desc = getattr(rel, "description", "") or ""
            meta: dict[str, Any] = {}
            if desc:
                try:
                    meta = json.loads(desc)
                except (json.JSONDecodeError, TypeError, ValueError):
                    meta = {"unlock_reason": desc}

            self._relations.append(
                {
                    "source_object": source,
                    "target_object": getattr(rel, "target_class", ""),
                    "target_action": resolve_action,
                    "unlock_reason": meta.get("unlock_reason") or resolve_action,
                    "unlock_hint": meta.get("unlock_hint", ""),
                    "relation_type": getattr(rel, "relation_type", ""),
                }
            )

        logger.debug(
            "OntologyRelationGraph: loaded %d ops_* relations",
            len(self._relations),
        )

    def get_next_objects(
        self,
        source_object: str,
    ) -> list[NextObjectSuggestion]:
        """返回 source_object 的所有关系对应的跳转目标（无条件全部解锁）。

        Args:
            source_object: 当前执行完工具的本体对象 code。

        Returns:
            NextObjectSuggestion 列表，每项对应一个要解锁的工具。
        """
        return [
            NextObjectSuggestion(
                object_code=rel["target_object"],
                tool=rel["target_action"],
                reason=rel["unlock_reason"],
                hint=rel["unlock_hint"],
                relation_type=rel["relation_type"],
            )
            for rel in self._relations
            if rel["source_object"] == source_object
        ]

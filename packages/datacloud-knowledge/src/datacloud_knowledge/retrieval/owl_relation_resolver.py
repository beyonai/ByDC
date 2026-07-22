"""OWL 关系遍历 — 解析视图/对象下的相关 OWL 术语。

数据库访问通过 ``create_reader()`` 的 ``get_relation_target_ids()`` 和
``get_terms_batch_raw()`` 完成，消除 raw sqlalchemy/get_session。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

from datacloud_knowledge.adapters import create_reader
from datacloud_knowledge.contracts.types import TermBrief

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


class _OwlRelationReader(Protocol):
    def get_relation_target_ids(
        self,
        *,
        source_term_ids: Sequence[str] | None = None,
        target_term_ids: Sequence[str] | None = None,
        relation_category: str | None = None,
    ) -> Sequence[str]: ...

    def get_terms_batch_raw(
        self,
        *,
        term_ids: Sequence[str] | None = None,
        term_codes: Sequence[str] | None = None,
    ) -> Sequence[dict[str, str | None]]: ...


def resolve_related_owl_terms(
    *,
    roots: list[dict[str, Any]],
) -> list[TermBrief]:
    collected: set[str] = set()
    reader = cast(_OwlRelationReader, create_reader())

    for root in roots or []:
        root_type = _normalize_type_code(str(root.get("term_type_code", "")).strip())
        if root_type not in ("ONTOLOGY_VIEW", "ONTOLOGY_OBJ"):
            raise TypeError(
                "roots[].term_type_code 仅支持 视图/对象(VIEW/OBJ 或 ONTOLOGY_VIEW/ONTOLOGY_OBJ)"
            )

        term_codes = root.get("term_codes") or []
        if not isinstance(term_codes, list):
            raise TypeError("roots[].term_codes 必须是数组")

        for term_id in term_codes:
            if not term_id:
                continue
            tid = str(term_id)
            root_terms = reader.get_terms_batch_raw(term_ids=[tid])
            if not root_terms:
                continue

            collected.add(tid)

            if root_type == "ONTOLOGY_VIEW":
                _collect_from_view_root(reader, tid, collected)
            else:
                _collect_from_obj_root(reader, tid, collected)

    # 最终一次性取回 term_name
    if not collected:
        return []
    rows = reader.get_terms_batch_raw(term_ids=sorted(collected))

    out: list[TermBrief] = []
    for row in rows:
        out.append(
            TermBrief(
                term_id=row["term_id"] or "",
                term_name=row["term_name"] or "",
            )
        )

    out.sort(key=lambda x: x.term_id)
    return out


def resolve_object_for_property(property_term_code: str) -> str | None:
    """给定属性 term_code，返回所属对象的 term_code。

    查找顺序：
    1. term_relation HAS_FIELD（对象 → 属性，反向查源）
    2. prop.parent_term_id 回退（属性的父术语即为对象）

    Args:
        property_term_code: 属性术语的业务编码。

    Returns:
        所属对象的 term_code，未找到返回 None。
    """
    if not property_term_code:
        return None

    reader = cast(_OwlRelationReader, create_reader())

    # 解析 property term_code → term_id
    prop_rows = reader.get_terms_batch_raw(term_codes=[property_term_code])
    if not prop_rows:
        return None

    prop_row = prop_rows[0]
    prop_term_id = prop_row.get("term_id")
    prop_parent_term_id = prop_row.get("parent_term_id")

    # Path 1: HAS_FIELD relation（反向查源：目标=属性，找源对象）
    if prop_term_id:
        object_term_ids = reader.get_relation_target_ids(
            target_term_ids=[prop_term_id],
            relation_category="HAS_FIELD",
        )
        if object_term_ids:
            obj_rows = reader.get_terms_batch_raw(term_ids=list(object_term_ids))
            for row in obj_rows:
                if _normalize_type_code(str(row.get("term_type_code") or "")) == "OBJ":
                    return row.get("term_code") or None

    # Path 2: parent_term_id 回退
    if prop_parent_term_id:
        parent_rows = reader.get_terms_batch_raw(term_ids=[prop_parent_term_id])
        if parent_rows:
            parent_row = parent_rows[0]
            if _normalize_type_code(str(parent_row.get("term_type_code") or "")) == "OBJ":
                return parent_row.get("term_code") or None

    return None


def _collect_from_view_root(reader: _OwlRelationReader, view_id: str, collected: set[str]) -> None:
    # hop1: VIEW(out) -> OBJ
    hop1_targets = _fetch_targets(reader, [view_id])
    obj_terms = _filter_by_type(_fetch_terms(reader, hop1_targets), "ONTOLOGY_OBJ")
    obj_ids = [t["term_id"] for t in obj_terms]
    collected.update(obj_ids)

    # hop2: OBJ(out) -> ACTION
    hop2_targets = _fetch_targets(reader, obj_ids)
    action_terms = _filter_by_type(_fetch_terms(reader, hop2_targets), "ONTOLOGY_ACTION")
    action_ids = [t["term_id"] for t in action_terms]
    collected.update(action_ids)

    # hop3: ACTION(out) -> FUNC
    hop3_targets = _fetch_targets(reader, action_ids)
    func_terms = _filter_by_type(_fetch_terms(reader, hop3_targets), "ONTOLOGY_FUNC")
    func_ids = [t["term_id"] for t in func_terms]
    collected.update(func_ids)


def _collect_from_obj_root(reader: _OwlRelationReader, obj_id: str, collected: set[str]) -> None:
    # hop1: OBJ(out) -> ACTION
    hop1_targets = _fetch_targets(reader, [obj_id])
    action_terms = _filter_by_type(_fetch_terms(reader, hop1_targets), "ONTOLOGY_ACTION")
    action_ids = [t["term_id"] for t in action_terms]
    collected.update(action_ids)

    # hop2: ACTION(out) -> FUNC
    hop2_targets = _fetch_targets(reader, action_ids)
    func_terms = _filter_by_type(_fetch_terms(reader, hop2_targets), "ONTOLOGY_FUNC")
    func_ids = [t["term_id"] for t in func_terms]
    collected.update(func_ids)


def _fetch_targets(reader: _OwlRelationReader, source_ids: list[str]) -> list[str]:
    if not source_ids:
        return []
    return list(reader.get_relation_target_ids(source_term_ids=source_ids))


def _fetch_terms(reader: _OwlRelationReader, term_ids: list[str]) -> list[dict[str, Any]]:
    if not term_ids:
        return []
    return list(reader.get_terms_batch_raw(term_ids=term_ids))


def _filter_by_type(terms: Iterable[dict[str, Any]], expected: str) -> list[dict[str, Any]]:
    exp = _normalize_type_code(expected)
    return [t for t in terms if _normalize_type_code(t.get("term_type_code") or "") == exp]


def _normalize_type_code(raw: str) -> str:
    """统一 type_code 格式。"""
    code = raw.strip()
    if code.startswith("ONTOLOGY_"):
        code = code[len("ONTOLOGY_") :]
    return code.upper()

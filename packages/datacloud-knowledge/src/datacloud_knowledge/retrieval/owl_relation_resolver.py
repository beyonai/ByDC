"""OWL 关系遍历 — 解析视图/对象下的相关 OWL 术语。

数据库访问通过 ``create_reader()`` 的 ``get_relation_target_ids()`` 和
``get_terms_batch_raw()`` 完成，消除 raw sqlalchemy/get_session。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from datacloud_knowledge.adapters import create_reader
from datacloud_knowledge.contracts.types import TermBrief

if TYPE_CHECKING:
    from collections.abc import Iterable


def resolve_related_owl_terms(
    *,
    roots: list[dict[str, Any]],
) -> list[TermBrief]:
    collected: set[str] = set()
    reader = create_reader()

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

    # 最终一次性取回 term_name/owl_doc_id，并过滤 owl_doc_id 非空
    if not collected:
        return []
    rows = reader.get_terms_batch_raw(term_ids=sorted(collected))

    out: list[TermBrief] = []
    for row in rows:
        owl = (row.get("owl_doc_id") or "").strip()
        if not owl:
            continue
        out.append(
            TermBrief(
                term_id=row["term_id"] or "",
                term_name=row["term_name"] or "",
                owl_doc_id=owl,
            )
        )

    out.sort(key=lambda x: x.term_id)
    return out


def _collect_from_view_root(reader: Any, view_id: str, collected: set[str]) -> None:
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


def _collect_from_obj_root(reader: Any, obj_id: str, collected: set[str]) -> None:
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


def _fetch_targets(reader: Any, source_ids: list[str]) -> list[str]:
    if not source_ids:
        return []
    return list(reader.get_relation_target_ids(source_term_ids=source_ids))


def _fetch_terms(reader: Any, term_ids: list[str]) -> list[dict[str, Any]]:
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

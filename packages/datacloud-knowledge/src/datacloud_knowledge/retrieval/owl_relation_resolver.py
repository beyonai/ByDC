from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from datacloud_knowledge.adapters.opengauss._db.connection import get_session
from datacloud_knowledge.adapters.opengauss._db.models import Term, TermRelation
from datacloud_knowledge.contracts.types import TermBrief

if TYPE_CHECKING:
    from collections.abc import Iterable


def resolve_related_owl_terms(
    *,
    roots: list[dict[str, Any]],
) -> list[TermBrief]:
    collected: set[str] = set()

    with get_session() as session:
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
                root_term = session.execute(
                    select(Term.term_id, Term.term_type_code).where(Term.term_id == tid)
                ).one_or_none()
                if root_term is None:
                    continue

                collected.add(tid)

                if root_type == "ONTOLOGY_VIEW":
                    _collect_from_view_root(session, tid, collected)
                else:
                    _collect_from_obj_root(session, tid, collected)

        # 最终一次性取回 term_name/owl_doc_id，并过滤 owl_doc_id 非空
        if not collected:
            return []
        rows = session.execute(
            select(Term.term_id, Term.term_name, Term.owl_doc_id).where(
                Term.term_id.in_(sorted(collected))
            )
        ).all()

    out: list[TermBrief] = []
    for term_id, term_name, owl_doc_id in rows:
        owl = (str(owl_doc_id) if owl_doc_id is not None else "").strip()
        if not owl:
            continue
        out.append(TermBrief(term_id=str(term_id), term_name=str(term_name), owl_doc_id=owl))

    out.sort(key=lambda x: x.term_id)
    return out


def _collect_from_view_root(session: Any, view_id: str, collected: set[str]) -> None:
    # hop1: VIEW(out) -> OBJ
    hop1_targets = _fetch_targets(session, [view_id])
    obj_terms = _filter_by_type(_fetch_terms(session, hop1_targets), "ONTOLOGY_OBJ")
    obj_ids = [t["term_id"] for t in obj_terms]
    collected.update(obj_ids)

    # hop2: OBJ(out) -> ACTION
    hop2_targets = _fetch_targets(session, obj_ids)
    action_terms = _filter_by_type(_fetch_terms(session, hop2_targets), "ONTOLOGY_ACTION")
    action_ids = [t["term_id"] for t in action_terms]
    collected.update(action_ids)

    # hop3: ACTION(out) -> FUNC
    hop3_targets = _fetch_targets(session, action_ids)
    func_terms = _filter_by_type(_fetch_terms(session, hop3_targets), "ONTOLOGY_FUNC")
    func_ids = [t["term_id"] for t in func_terms]
    collected.update(func_ids)


def _collect_from_obj_root(session: Any, obj_id: str, collected: set[str]) -> None:
    # hop1: OBJ(out) -> ACTION
    hop1_targets = _fetch_targets(session, [obj_id])
    action_terms = _filter_by_type(_fetch_terms(session, hop1_targets), "ONTOLOGY_ACTION")
    action_ids = [t["term_id"] for t in action_terms]
    collected.update(action_ids)

    # hop2: ACTION(out) -> FUNC
    hop2_targets = _fetch_targets(session, action_ids)
    func_terms = _filter_by_type(_fetch_terms(session, hop2_targets), "ONTOLOGY_FUNC")
    func_ids = [t["term_id"] for t in func_terms]
    collected.update(func_ids)


def _fetch_targets(session: Any, source_ids: list[str]) -> list[str]:
    if not source_ids:
        return []
    rows = session.execute(
        select(TermRelation.target_term_id)
        .where(TermRelation.source_term_id.in_(source_ids))
        .distinct()
    ).all()
    return [str(r[0]) for r in rows if r and r[0]]


def _fetch_terms(session: Any, term_ids: list[str]) -> list[dict[str, Any]]:
    if not term_ids:
        return []
    rows = session.execute(
        select(Term.term_id, Term.term_name, Term.term_type_code, Term.owl_doc_id).where(
            Term.term_id.in_(term_ids)
        )
    ).all()
    return [
        {
            "term_id": str(term_id),
            "term_name": str(term_name),
            "term_type_code": str(term_type_code),
            "owl_doc_id": None if owl_doc_id is None else str(owl_doc_id),
        }
        for term_id, term_name, term_type_code, owl_doc_id in rows
    ]


def _filter_by_type(terms: Iterable[dict[str, Any]], expected: str) -> list[dict[str, Any]]:
    exp = _normalize_type_code(expected)
    return [t for t in terms if _normalize_type_code(t.get("term_type_code") or "") == exp]


def _normalize_type_code(type_code: str) -> str:
    raw = (type_code or "").strip()
    if not raw:
        return raw
    mapping = {
        "ONTOLOGY_VIEW": "view",
        "ONTOLOGY_OBJ": "object",
        "ONTOLOGY_ACTION": "action",
        "ONTOLOGY_FUNC": "func",
        "ONTOLOGY_PARAM": "param",
        "ONTOLOGY_PROP": "prop",
        "VIEW": "view",
        "OBJ": "object",
        "ACTION": "action",
        "FUNC": "func",
        "PARAM": "param",
        "PROP": "prop",
    }
    return mapping.get(raw, raw)

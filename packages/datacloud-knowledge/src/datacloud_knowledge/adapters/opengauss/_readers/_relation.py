"""_RelationReader — Mixin providing TermRelation read operations for the OpenGauss adapter.

Supports term-relation and term-type-relation queries with keyword search and pagination.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import aliased

from datacloud_knowledge.adapters.opengauss._db.models import Term, TermRelation
from datacloud_knowledge.adapters.opengauss._readers._base import _ReaderBase

logger = logging.getLogger(__name__)


class _RelationReader(_ReaderBase):
    """Mixin that reads ``term_relation`` table rows via the shared reader base."""

    def list_term_relations(
        self,
        *,
        source_term_id: str | None = None,
        target_term_id: str | None = None,
        relation_category: str | None = None,
        relation_code: str | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """List term relations with optional filters, keyword search, and pagination.

        Args:
            source_term_id: Filter by source term ID.
            target_term_id: Filter by target term ID.
            relation_category: Filter by relation category.
            keyword: Optional keyword, searches relation_name (ILIKE).
            page_index: 1-based page number (default 1).
            page_size: Items per page (default 20, max 100).

        Returns:
            Dict with ``data``, ``pageIndex``, ``pageSize``, ``totalCount``, ``totalPages``.
            Each relation includes source/target term names.
        """
        page_size = min(page_size, 100)
        offset = (page_index - 1) * page_size

        conditions: list[Any] = []
        params: dict[str, Any] = {}

        if source_term_id is not None:
            conditions.append(TermRelation.source_term_id == source_term_id)
        if target_term_id is not None:
            conditions.append(TermRelation.target_term_id == target_term_id)
        if relation_category is not None:
            conditions.append(TermRelation.relation_category == relation_category)
        if relation_code is not None:
            conditions.append(TermRelation.ext_attrs["relation_code"].astext == relation_code)
        if keyword and keyword.strip():
            conditions.append(text("term_relation.relation_name ILIKE :kw"))
            params["kw"] = f"%{keyword.strip()}%"

        where_clause = and_(*conditions) if conditions else text("1=1")

        try:
            with self._get_session() as session:
                total = int(
                    session.execute(
                        select(func.count()).select_from(TermRelation).where(where_clause),
                        params,
                    ).scalar_one()
                )

                if total == 0:
                    return {
                        "data": [],
                        "pageIndex": page_index,
                        "pageSize": page_size,
                        "totalCount": 0,
                        "totalPages": 0,
                    }

                rows = session.execute(
                    select(
                        TermRelation.relation_id,
                        TermRelation.source_term_id,
                        TermRelation.source_term_type_code,
                        TermRelation.target_term_id,
                        TermRelation.target_term_type_code,
                        TermRelation.relation_name,
                        TermRelation.relation_category,
                        TermRelation.cardinality,
                        TermRelation.ext_attrs,
                        TermRelation.created_time,
                        TermRelation.updated_time,
                    )
                    .where(where_clause)
                    .order_by(TermRelation.relation_name)
                    .limit(page_size)
                    .offset(offset),
                    params,
                ).all()

                # Collect all term_ids for batch name resolution
                term_ids: set[str] = set()
                for row in rows:
                    if row[1]:
                        term_ids.add(str(row[1]))
                    if row[3]:
                        term_ids.add(str(row[3]))

                term_name_map = self._batch_get_term_names(session, term_ids)

        except Exception:
            logger.exception(
                "list_term_relations failed: source=%s target=%s category=%s keyword=%s",
                source_term_id,
                target_term_id,
                relation_category,
                keyword,
            )
            raise

        data = [
            {
                "relation_id": str(row[0]),
                "source_term_id": str(row[1]) if row[1] else None,
                "source_term_type_code": str(row[2]) if row[2] else None,
                "target_term_id": str(row[3]) if row[3] else None,
                "target_term_type_code": str(row[4]) if row[4] else None,
                "relation_name": str(row[5]),
                "relation_category": str(row[6]),
                "cardinality": str(row[7]) if row[7] else None,
                "ext_attrs": dict(row[8]) if isinstance(row[8], dict) else {},
                "created_time": self._format_time(row[9]),
                "updated_time": self._format_time(row[10]),
                "source_term_name": term_name_map.get(str(row[1])) if row[1] else None,
                "target_term_name": term_name_map.get(str(row[3])) if row[3] else None,
            }
            for row in rows
        ]

        return {
            "data": data,
            "pageIndex": page_index,
            "pageSize": page_size,
            "totalCount": total,
            "totalPages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        }

    def get_term_relation(self, *, relation_id: str) -> dict[str, Any] | None:
        """Get a single term relation by its ID.

        Args:
            relation_id: The relation's primary key.

        Returns:
            Dict with relation fields, or None if not found.
        """
        try:
            with self._get_session() as session:
                row = session.execute(
                    select(
                        TermRelation.relation_id,
                        TermRelation.source_term_id,
                        TermRelation.source_term_type_code,
                        TermRelation.target_term_id,
                        TermRelation.target_term_type_code,
                        TermRelation.relation_name,
                        TermRelation.relation_category,
                        TermRelation.cardinality,
                        TermRelation.ext_attrs,
                        TermRelation.created_time,
                        TermRelation.updated_time,
                    ).where(TermRelation.relation_id == relation_id)
                ).first()
        except Exception:
            logger.exception("get_term_relation failed: relation_id=%s", relation_id)
            raise

        if row is None:
            return None

        return {
            "relation_id": str(row[0]),
            "source_term_id": str(row[1]) if row[1] else None,
            "source_term_type_code": str(row[2]) if row[2] else None,
            "target_term_id": str(row[3]) if row[3] else None,
            "target_term_type_code": str(row[4]) if row[4] else None,
            "relation_name": str(row[5]),
            "relation_category": str(row[6]),
            "cardinality": str(row[7]) if row[7] else None,
            "ext_attrs": dict(row[8]) if isinstance(row[8], dict) else {},
            "created_time": self._format_time(row[9]),
            "updated_time": self._format_time(row[10]),
        }

    def list_term_type_relations(
        self,
        *,
        library_id: str,
        type_code: str,
        direction: str = "both",
        relation_category: str | None = None,
        relation_code: str | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """List relations involving a term type (ADR-006 修复: JOIN term 表做类型过滤).

        冗余列 term_relation.source_term_type_code / target_term_type_code 从未被写入
        （全 NULL），因此不再用它做过滤条件。改为 JOIN 权威表 term
        （term.term_type_code NOT NULL），过滤语义为"给定术语类型 type_code，
        查该类型术语参与的所有关系"：

        - direction=outgoing → source 端术语的 term_type_code == type_code（INNER JOIN）
        - direction=incoming → target 端术语的 term_type_code == type_code（INNER JOIN）
        - direction=both     → 双别名 LEFT JOIN，任一端类型匹配即命中
        - type_code 为空     → 不过滤（向后兼容，返回全部关系）

        Args:
            library_id: Term library ID.
            type_code: Term type code. 空字符串视为未提供（不过滤）。
            direction: "outgoing" (type is source), "incoming" (type is target),
                       or "both" (default).
            relation_category: Optional relation category filter.
            relation_code: Optional relation code filter (ext_attrs.relation_code).
            keyword: Optional keyword for relation_name (ILIKE).
            page_index: 1-based page number (default 1).
            page_size: Items per page (default 20, max 100).

        Returns:
            Dict with ``data`` (list of relation dicts with source/target type indicators),
            ``pageIndex``, ``pageSize``, ``totalCount``, ``totalPages``.
        """
        page_size = min(page_size, 100)
        offset = (page_index - 1) * page_size

        conditions: list[Any] = []
        exec_params: dict[str, Any] = {}

        if relation_category:
            conditions.append(TermRelation.relation_category == relation_category)

        if relation_code:
            conditions.append(
                TermRelation.ext_attrs["relation_code"].astext == relation_code
            )

        if keyword and keyword.strip():
            conditions.append(text("term_relation.relation_name ILIKE :kw"))
            exec_params["kw"] = f"%{keyword.strip()}%"

        where_clause = and_(*conditions) if conditions else text("1=1")

        # ── JOIN term 表（权威 term_type_code）做类型过滤 ─────────────────────
        # 方案 A：废弃冗余列 source/target_term_type_code（全 NULL）。
        # - outgoing/incoming 用 INNER JOIN：语义上"该类型术语必须存在于 term 表"，
        #   term.term_type_code 为 NOT NULL，left+where 判空与 inner 等价，inner 更直白；
        # - both 必须用 LEFT JOIN ×2：term_relation.source/target_term_id 可空，
        #   INNER JOIN 会因另一端 JOIN 失败而误删本应命中的行，LEFT + OR 保证
        #   任一端类型匹配即保留。
        src_term = aliased(Term)
        tgt_term = aliased(Term)

        def _join_and_filter(
            stmt: Any,
        ) -> tuple[Any, Any, Any | None, Any | None]:
            """给 stmt 追加 term JOIN 与类型过滤；count 与主查询共用本函数。

            Returns:
                (stmt, type_filter, src_type_col, tgt_type_col)
                - type_filter: 附加 WHERE 条件；type_code 为空时为 None（不过滤）
                - src_type_col/tgt_type_col: 主查询追加的 term.term_type_code
                  列（带 label），供 direction 判定使用
            """
            if not type_code:
                return stmt, None, None, None
            if direction == "outgoing":
                joined = stmt.join(
                    src_term, TermRelation.source_term_id == src_term.term_id
                )
                return (
                    joined,
                    src_term.term_type_code == type_code,
                    src_term.term_type_code.label("src_join_type"),
                    None,
                )
            if direction == "incoming":
                joined = stmt.join(
                    tgt_term, TermRelation.target_term_id == tgt_term.term_id
                )
                return (
                    joined,
                    tgt_term.term_type_code == type_code,
                    None,
                    tgt_term.term_type_code.label("tgt_join_type"),
                )
            joined = stmt.outerjoin(
                src_term, TermRelation.source_term_id == src_term.term_id
            ).outerjoin(tgt_term, TermRelation.target_term_id == tgt_term.term_id)
            return (
                joined,
                or_(
                    src_term.term_type_code == type_code,
                    tgt_term.term_type_code == type_code,
                ),
                src_term.term_type_code.label("src_join_type"),
                tgt_term.term_type_code.label("tgt_join_type"),
            )

        # count 与主查询共用同一 JOIN + WHERE，保证 totalCount 不失真
        count_stmt, count_filter, _, _ = _join_and_filter(
            select(func.count()).select_from(TermRelation)
        )
        if count_filter is not None:
            count_stmt = count_stmt.where(count_filter)

        try:
            with self._get_session() as session:
                total = int(
                    session.execute(
                        count_stmt.where(where_clause), exec_params
                    ).scalar_one()
                )

                if total == 0:
                    return {
                        "data": [],
                        "pageIndex": page_index,
                        "pageSize": page_size,
                        "totalCount": 0,
                        "totalPages": 0,
                    }

                rows_stmt, type_filter, src_type_col, tgt_type_col = _join_and_filter(
                    select(
                        TermRelation.relation_id,
                        TermRelation.source_term_id,
                        TermRelation.source_term_type_code,
                        TermRelation.target_term_id,
                        TermRelation.target_term_type_code,
                        TermRelation.relation_name,
                        TermRelation.relation_category,
                        TermRelation.cardinality,
                        TermRelation.created_time,
                        TermRelation.updated_time,
                    )
                )
                if type_filter is not None:
                    rows_stmt = rows_stmt.where(type_filter)
                if src_type_col is not None:
                    rows_stmt = rows_stmt.add_columns(src_type_col)
                if tgt_type_col is not None:
                    rows_stmt = rows_stmt.add_columns(tgt_type_col)

                rows = session.execute(
                    rows_stmt.where(where_clause)
                    .order_by(TermRelation.relation_name)
                    .limit(page_size)
                    .offset(offset),
                    exec_params,
                ).all()

                # Batch resolve term/type names
                term_ids: set[str] = set()
                type_codes: set[str] = set()
                for row in rows:
                    if row[1]:
                        term_ids.add(str(row[1]))
                    if row[2]:
                        type_codes.add(str(row[2]))
                    if row[3]:
                        term_ids.add(str(row[3]))
                    if row[4]:
                        type_codes.add(str(row[4]))

                term_name_map = self._batch_get_term_names(session, term_ids)
                type_name_map = self._batch_get_type_names(session, type_codes)

        except Exception:
            logger.exception(
                "list_term_type_relations failed: library_id=%s type_code=%s direction=%s",
                library_id,
                type_code,
                direction,
            )
            raise

        data = []
        for row in rows:
            src_term_id = str(row[1]) if row[1] else None
            src_type_code = str(row[2]) if row[2] else None
            tgt_term_id = str(row[3]) if row[3] else None
            tgt_type_code = str(row[4]) if row[4] else None

            # direction 判定：优先看 JOIN 命中的 term.term_type_code（权威列）。
            # type_code 为空（不过滤）时回退冗余列比较，保持旧行为。
            src_join_type = row._mapping.get("src_join_type")
            if type_code and direction == "outgoing":
                is_outgoing = True
            elif type_code and direction == "incoming":
                is_outgoing = False
            elif type_code:
                is_outgoing = bool(src_join_type) and str(src_join_type) == type_code
            else:
                is_outgoing = src_type_code == type_code

            source: dict[str, Any]
            if src_term_id:
                source = {
                    "type": "term",
                    "term_id": src_term_id,
                    "term_code": None,
                    "term_name": term_name_map.get(src_term_id),
                }
            elif src_type_code:
                source = {
                    "type": "term_type",
                    "type_code": src_type_code,
                    "type_name": type_name_map.get(src_type_code),
                }
            else:
                source = {"type": "unknown"}

            target: dict[str, Any]
            if tgt_term_id:
                target = {
                    "type": "term",
                    "term_id": tgt_term_id,
                    "term_code": None,
                    "term_name": term_name_map.get(tgt_term_id),
                }
            elif tgt_type_code:
                target = {
                    "type": "term_type",
                    "type_code": tgt_type_code,
                    "type_name": type_name_map.get(tgt_type_code),
                }
            else:
                target = {"type": "unknown"}

            data.append(
                {
                    "relation_id": str(row[0]),
                    "relation_name": str(row[5]),
                    "relation_category": str(row[6]),
                    "cardinality": str(row[7]) if row[7] else None,
                    "direction": "outgoing" if is_outgoing else "incoming",
                    "source": source,
                    "target": target,
                    "created_time": self._format_time(row[8]),
                    "updated_time": self._format_time(row[9]),
                }
            )

        return {
            "data": data,
            "pageIndex": page_index,
            "pageSize": page_size,
            "totalCount": total,
            "totalPages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        }

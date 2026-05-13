"""子串召回 — 术语名是查询文本的子串时召回，按长度降序排列。

适用于查询文本较长、术语名较短的场景（如 "高风险企业" 能召回 "高风险"）。
同时也处理查询文本是术语名子串的情况（如 "风险" 能召回 "中风险"、"高风险"）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import bindparam, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def substring_recall(
    session: Session,
    query_text: str,
    *,
    top_k: int = 20,
    term_type_codes: set[str] | None = None,
) -> list[tuple[str, str, str, str, str]]:
    """执行双向子串匹配召回。

    匹配逻辑：
    1. 术语名是查询文本的子串（term_name IN query_text）
    2. 查询文本是术语名的子串（query_text IN term_name）

    结果按匹配术语名长度降序排列（越长越精确）。

    Args:
        session: SQLAlchemy Session。
        query_text: 用户输入的查询文本。
        top_k: 最大返回数量。
        term_type_codes: 可选的 term_type_code 白名单过滤。

    Returns:
        ``(term_id, term_name, name_id, term_type_code, term_code)`` 列表，按名称长度降序。
    """
    query_text = query_text.strip()
    if not query_text:
        return []

    if term_type_codes:
        type_codes_list = sorted(term_type_codes)
        sql = text("""
            SELECT
                tn.term_id,
                tn.name_text AS term_name,
                tn.name_id,
                t.term_type_code,
                t.term_code
            FROM
                term_name tn
                JOIN term t ON tn.term_id = t.term_id
            WHERE
                (
                    POSITION(tn.name_text IN :query_text) > 0
                    OR POSITION(:query_text IN tn.name_text) > 0
                )
                AND t.term_type_code IN :type_codes
            ORDER BY
                LENGTH(tn.name_text) DESC
            LIMIT :limit
        """).bindparams(
            bindparam("type_codes", expanding=True),
        )
        params: dict[str, object] = {
            "query_text": query_text,
            "type_codes": type_codes_list,
            "limit": top_k,
        }
    else:
        sql = text("""
            SELECT
                tn.term_id,
                tn.name_text AS term_name,
                tn.name_id,
                t.term_type_code,
                t.term_code
            FROM
                term_name tn
                JOIN term t ON tn.term_id = t.term_id
            WHERE
                (
                    POSITION(tn.name_text IN :query_text) > 0
                    OR POSITION(:query_text IN tn.name_text) > 0
                )
            ORDER BY
                LENGTH(tn.name_text) DESC
            LIMIT :limit
        """)
        params = {"query_text": query_text, "limit": top_k}

    try:
        rows = session.execute(sql, params).fetchall()
        return [
            (str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]) if row[4] else "")
            for row in rows
        ]
    except Exception:
        log.exception("Substring recall failed for '%s'", query_text)
        raise


def substring_recall_partitioned(
    session: Session,
    query_text: str,
    *,
    per_type_limit: int = 3,
    term_type_codes: set[str] | None = None,
) -> list[tuple[str, str, str, str, str]]:
    """双向子串匹配召回，按 term_type_code 分区取 top per_type_limit。"""
    query_text = query_text.strip()
    if not query_text or not term_type_codes:
        return []

    type_codes_list = sorted(term_type_codes)
    sql = text("""
        SELECT term_id, term_name, name_id, term_type_code, term_code
        FROM (
            SELECT
                tn.term_id,
                tn.name_text AS term_name,
                tn.name_id,
                t.term_type_code,
                t.term_code,
                ROW_NUMBER() OVER (
                    PARTITION BY t.term_type_code
                    ORDER BY LENGTH(tn.name_text) DESC
                ) AS rn
            FROM
                term_name tn
                JOIN term t ON tn.term_id = t.term_id
            WHERE
                (
                    POSITION(tn.name_text IN :query_text) > 0
                    OR POSITION(:query_text IN tn.name_text) > 0
                )
                AND t.term_type_code IN :type_codes
        ) ranked
        WHERE rn <= :per_type_limit
        ORDER BY LENGTH(term_name) DESC
    """).bindparams(
        bindparam("type_codes", expanding=True),
    )
    params: dict[str, object] = {
        "query_text": query_text,
        "type_codes": type_codes_list,
        "per_type_limit": per_type_limit,
    }
    try:
        rows = session.execute(sql, params).fetchall()
        return [
            (str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]) if row[4] else "")
            for row in rows
        ]
    except Exception:
        log.exception("Substring partitioned recall failed for '%s'", query_text)
        raise

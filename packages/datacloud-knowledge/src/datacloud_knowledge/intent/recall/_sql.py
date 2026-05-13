"""批量召回 SQL 构建层：tsquery / substring / vector 查询生成与执行。

包含 VALUES 子句生成、scope 过滤子句、窗口函数 SQL、查询执行以及行收集。
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from sqlalchemy import bindparam, text

from ._models import _BM25_MIN_SCORE, RecallRequest

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _build_values_clause(
    requests: list[RecallRequest],
    *,
    value_getter: Callable[[RecallRequest], str],
    cast_type: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """生成批量 VALUES (:keyword_key, :value) 子句与绑定参数。"""
    values_sql: list[str] = []
    params: dict[str, Any] = {}
    for index, request in enumerate(requests):
        keyword_key_name = f"keyword_key_{index}"
        value_name = f"value_{index}"
        value_expr = f":{value_name}"
        if cast_type is not None:
            value_expr = f"CAST(:{value_name} AS {cast_type})"
        values_sql.append(f"(:{keyword_key_name}, {value_expr})")
        params[keyword_key_name] = request.map_key
        params[value_name] = value_getter(request)
    return ", ".join(values_sql), params


def _build_effective_scope_clause(scope_code: str | None, *, strict: bool = False) -> str:
    """Build scope SQL clause for recall filtering.

    Args:
        scope_code: View/object code to filter by. Empty = no filter.
        strict: If True, exclude legacy ``search_scope = '{}'`` rows.
                Use strict=True for ontology-term recall (prop aliases only).
                Use strict=False for value-term recall (enterprise names etc.).

    Notes:
        ``search_scope = '{}'`` rows are only allowed when their term belongs to the
        current ontology root subtree anchored at ``scope_code``.
    """
    if not scope_code:
        return ""
    base = """
                  AND (
                        tn.search_scope @> CAST(:view_scope AS jsonb)
                        OR tn.search_scope @> CAST(:obj_scope AS jsonb)
                        OR tn.search_scope @> CAST('{"scope":"global"}' AS jsonb)"""
    if strict:
        return base + "\n                  )"
    return (
        base
        + """
                        OR (
                             tn.search_scope = '{}'::jsonb
                             AND EXISTS (
                                 SELECT 1
                                 FROM term root
                                 JOIN term_relation tr ON tr.source_term_id = root.term_id
                                 JOIN term prop ON prop.term_id = tr.target_term_id
                                 JOIN term child ON child.parent_term_id = prop.term_id
                                 WHERE root.term_code = :scope_code
                                   AND root.term_type_code IN ('view', 'object')
                                   AND root.library_id = t.library_id
                                   AND child.term_id = t.term_id
                             )
                        )
                  )"""
    )


def _build_scope_params(scope_code: str | None) -> dict[str, str]:
    """为 scope 过滤生成绑定参数（view_scope / obj_scope JSON 值）。"""
    if not scope_code:
        return {}
    return {
        "scope_code": scope_code,
        "view_scope": json.dumps({"scope": "view", "code": scope_code}),
        "obj_scope": json.dumps({"scope": "object", "code": scope_code}),
    }


def _build_tsquery_sql(
    *,
    input_values: str,
    tsvector_column: str,
    order_expr: str,
    type_filter: frozenset[str] | None,
    per_type_limit: int = 0,
    scope_clause: str = "",
) -> object:
    """构建 tsquery 窗口函数 SQL（兼顾 per-type 与普通模式）。"""
    type_clause = ""
    if type_filter is not None:
        type_clause = "\n            AND t.term_type_code IN :type_codes"

    if per_type_limit > 0:
        sql = f"""
            WITH input(keyword_key, tsquery_text) AS (
              VALUES {input_values}
            ), ranked AS (
              SELECT i.keyword_key,
                     tn.term_id,
                     tn.name_text AS term_name,
                     tn.name_id,
                     t.term_type_code,
                     ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) AS score,
                     t.term_code,
                     ROW_NUMBER() OVER (
                       PARTITION BY i.keyword_key, t.term_type_code
                       ORDER BY ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) DESC
                     ) AS rn
              FROM input i
              JOIN term_name tn ON tn.{tsvector_column} @@ to_tsquery('simple', i.tsquery_text)
              JOIN term t ON tn.term_id = t.term_id
              WHERE tn.{tsvector_column} IS NOT NULL{type_clause}{scope_clause}
            )
            SELECT keyword_key, term_id, term_name, name_id, term_type_code, score, term_code
            FROM ranked
            WHERE rn <= :per_type_limit AND score >= :min_score
            ORDER BY keyword_key, score DESC
        """
        sql_obj = text(sql)
    else:
        sql = f"""
            WITH input(keyword_key, tsquery_text) AS (
              VALUES {input_values}
            ), ranked AS (
              SELECT i.keyword_key,
                     tn.term_id,
                     tn.name_text AS term_name,
                     tn.name_id,
                     t.term_type_code,
                     ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) AS score,
                     t.term_code,
                     ROW_NUMBER() OVER (
                       PARTITION BY i.keyword_key
                       ORDER BY ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) DESC
                     ) AS rn
              FROM input i
              JOIN term_name tn ON tn.{tsvector_column} @@ to_tsquery('simple', i.tsquery_text)
              JOIN term t ON tn.term_id = t.term_id
              WHERE tn.{tsvector_column} IS NOT NULL{type_clause}{scope_clause}
                AND ts_rank_cd(tn.{tsvector_column}, to_tsquery('simple', i.tsquery_text), 32) >= :min_score
            )
            SELECT keyword_key, term_id, term_name, name_id, term_type_code, score, term_code
            FROM ranked
            WHERE rn <= :per_kw_limit
            ORDER BY keyword_key, score DESC
        """
        sql_obj = text(sql)

    if type_filter is not None:
        return sql_obj.bindparams(bindparam("type_codes", expanding=True))
    return sql_obj


def _build_substring_sql(
    *,
    input_values: str,
    type_filter: frozenset[str] | None,
    per_type_limit: int = 0,
    scope_clause: str = "",
) -> object:
    """构建子串匹配窗口函数 SQL（兼顾 per-type 与普通模式）。"""
    type_clause = ""
    if type_filter is not None:
        type_clause = "\n                  AND t.term_type_code IN :type_codes"

    if per_type_limit > 0:
        sql = f"""
            WITH input(keyword_key, keyword_text) AS (
              VALUES {input_values}
            ), ranked AS (
              SELECT i.keyword_key,
                     tn.term_id,
                     tn.name_text AS term_name,
                     tn.name_id,
                     t.term_type_code,
                     LENGTH(tn.name_text)::float AS score,
                     t.term_code,
                     ROW_NUMBER() OVER (
                       PARTITION BY i.keyword_key, t.term_type_code
                       ORDER BY LENGTH(tn.name_text) DESC
                     ) AS rn
              FROM input i
              JOIN term_name tn ON (
                    POSITION(tn.name_text IN i.keyword_text) > 0
                    OR POSITION(i.keyword_text IN tn.name_text) > 0
                  )
              JOIN term t ON tn.term_id = t.term_id
              WHERE 1 = 1{type_clause}{scope_clause}
            )
            SELECT keyword_key, term_id, term_name, name_id, term_type_code, score, term_code
            FROM ranked
            WHERE rn <= :per_type_limit
            ORDER BY keyword_key, score DESC
        """
        sql_obj = text(sql)
    else:
        sql = f"""
            WITH input(keyword_key, keyword_text) AS (
              VALUES {input_values}
            ), ranked AS (
              SELECT i.keyword_key,
                     tn.term_id,
                     tn.name_text AS term_name,
                     tn.name_id,
                     t.term_type_code,
                     LENGTH(tn.name_text)::float AS score,
                     t.term_code,
                     ROW_NUMBER() OVER (
                       PARTITION BY i.keyword_key
                       ORDER BY LENGTH(tn.name_text) DESC
                     ) AS rn
              FROM input i
              JOIN term_name tn ON (
                    POSITION(tn.name_text IN i.keyword_text) > 0
                    OR POSITION(i.keyword_text IN tn.name_text) > 0
                  )
              JOIN term t ON tn.term_id = t.term_id
              WHERE 1 = 1{type_clause}{scope_clause}
            )
            SELECT keyword_key, term_id, term_name, name_id, term_type_code, score, term_code
            FROM ranked
            WHERE rn <= :per_kw_limit
            ORDER BY keyword_key, score DESC
        """
        sql_obj = text(sql)

    if type_filter is not None:
        return sql_obj.bindparams(bindparam("type_codes", expanding=True))
    return sql_obj


def _build_vector_sql(*, typed: bool, per_type: bool, scope_clause: str = "") -> object:
    """构建向量召回 SQL（支持 typed 过滤与 per-type 分区）。"""
    type_clause = ""
    if typed:
        type_clause = "\n              AND t.term_type_code IN :type_codes"

    if per_type:
        sql = f"""
            SELECT term_id, term_name, name_id, term_type_code, score, term_code
            FROM (
                SELECT top_n.term_id,
                       top_n.term_name,
                       top_n.name_id,
                       top_n.term_type_code,
                       top_n.score,
                       top_n.term_code,
                       ROW_NUMBER() OVER (
                          PARTITION BY top_n.term_type_code
                          ORDER BY top_n.score DESC
                       ) AS rn
                FROM (
                    SELECT tn.term_id,
                           tn.name_text AS term_name,
                           tn.name_id,
                           t.term_type_code,
                           1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS score,
                           t.term_code
                    FROM term_name tn
                    JOIN term t ON tn.term_id = t.term_id
                    WHERE tn.name_embedding IS NOT NULL{type_clause}{scope_clause}
                    ORDER BY tn.name_embedding <=> CAST(:vector AS vector)
                    LIMIT :limit
                ) top_n
            ) ranked
            WHERE rn <= :per_type_limit AND score >= :min_similarity
            ORDER BY score DESC
        """
    else:
        sql = f"""
            SELECT tn.term_id,
                   tn.name_text AS term_name,
                   tn.name_id,
                   t.term_type_code,
                   1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS score,
                   t.term_code
            FROM term_name tn
            JOIN term t ON tn.term_id = t.term_id
            WHERE tn.name_embedding IS NOT NULL{type_clause}{scope_clause}
            ORDER BY tn.name_embedding <=> CAST(:vector AS vector)
            LIMIT :limit
        """

    sql_obj = text(sql)
    if typed:
        return sql_obj.bindparams(bindparam("type_codes", expanding=True))
    return sql_obj


def _group_requests_by_filter(
    requests: tuple[RecallRequest, ...],
) -> dict[frozenset[str] | None, list[RecallRequest]]:
    """按 type_filter 分组请求，同组共享一条 SQL。"""
    grouped: dict[frozenset[str] | None, list[RecallRequest]] = defaultdict(list)
    for request in requests:
        grouped[request.type_filter].append(request)
    return grouped


def _run_tsquery_query(
    session: Session,
    requests: list[RecallRequest],
    type_filter: frozenset[str] | None,
    *,
    top_k: int,
    column_name: str,
    tokenizer: Callable[[str], str],
    per_type_limit: int = 0,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """执行一条 tsquery 批量查询并返回分组行。"""
    scope_code = requests[0].scope_code if requests else None
    # ontology-term recall (select/groupBy/orderBy/whereKey) uses strict scope;
    # value-term recall (whereValue) allows legacy unscoped rows
    is_strict = bool(requests) and not requests[0].is_value_recall
    scope_clause = _build_effective_scope_clause(scope_code, strict=is_strict)
    input_values, params = _build_values_clause(
        requests,
        value_getter=lambda request: str(tokenizer(request.keyword)),
    )
    if per_type_limit > 0:
        sql = _build_tsquery_sql(
            input_values=input_values,
            tsvector_column=column_name,
            order_expr="score DESC",
            type_filter=type_filter,
            per_type_limit=per_type_limit,
            scope_clause=scope_clause,
        )
        params["per_type_limit"] = per_type_limit
    else:
        sql = _build_tsquery_sql(
            input_values=input_values,
            tsvector_column=column_name,
            order_expr="score DESC",
            type_filter=type_filter,
            scope_clause=scope_clause,
        )
        params["per_kw_limit"] = top_k * 3

    params["min_score"] = _BM25_MIN_SCORE
    if type_filter is not None:
        params["type_codes"] = sorted(type_filter)
    if scope_clause:
        params.update(_build_scope_params(scope_code))
    statement: Any = sql
    return _collect_ranked_rows(session.execute(statement, params).fetchall())


def _run_substring_query(
    session: Session,
    requests: list[RecallRequest],
    type_filter: frozenset[str] | None,
    *,
    top_k: int,
    per_type_limit: int = 0,
) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """执行一条子串匹配批量查询并返回分组行。"""
    scope_code = requests[0].scope_code if requests else None
    is_strict = bool(requests) and not requests[0].is_value_recall
    scope_clause = _build_effective_scope_clause(scope_code, strict=is_strict)
    input_values, params = _build_values_clause(
        requests,
        value_getter=lambda request: request.keyword,
    )
    if per_type_limit > 0:
        sql = _build_substring_sql(
            input_values=input_values,
            type_filter=type_filter,
            per_type_limit=per_type_limit,
            scope_clause=scope_clause,
        )
        params["per_type_limit"] = per_type_limit
    else:
        sql = _build_substring_sql(
            input_values=input_values,
            type_filter=type_filter,
            scope_clause=scope_clause,
        )
        params["per_kw_limit"] = top_k * 3
    if type_filter is not None:
        params["type_codes"] = sorted(type_filter)
    if scope_clause:
        params.update(_build_scope_params(scope_code))
    statement: Any = sql
    return _collect_ranked_rows(session.execute(statement, params).fetchall())


def _collect_ranked_rows(rows: Any) -> dict[str, list[tuple[str, str, str, str, str]]]:
    """将查询返回的扁平行按 keyword_key 分组。"""
    grouped: dict[str, list[tuple[str, str, str, str, str]]] = defaultdict(list)
    for keyword_key, term_id, term_name, name_id, term_type_code, _score, term_code in rows:
        grouped[str(keyword_key)].append(
            (
                str(term_id),
                str(term_name),
                str(name_id),
                str(term_type_code),
                str(term_code),
            )
        )
    return dict(grouped)

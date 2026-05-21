"""PostgreSQL 术语搜索引擎实现。

实现 TermSearchEngine 协议的三路召回策略：
- BM25: PostgreSQL tsvector + ts_rank_cd 全文搜索
- Substring: 双向子串匹配（术语名⊆查询 OR 查询⊆术语名）
- Vector: pgvector HNSW 余弦相似度搜索

通过 Tokenizer 协议解耦分词策略，支持中英文等多种语言。
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, suppress
from typing import TYPE_CHECKING, Any

from sqlalchemy import bindparam, text

from datacloud_knowledge.adapters.opengauss._db.connection import get_session
from datacloud_knowledge.adapters.opengauss._db.url import resolve_knowledge_schema
from datacloud_knowledge.contracts.protocols import TermSearchEngine
from datacloud_knowledge.contracts.text import Tokenizer
from datacloud_knowledge.contracts.types import BM25Result, SubstringResult, VectorResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from datacloud_knowledge.retrieval.recall._models import RecallRequest

log = logging.getLogger(__name__)

# 进程级列存在性缓存（减少 information_schema 重复查询）
_COLUMN_CAPS_CACHE: dict[str, bool] = {}

# term_name 表常量
_TABLE = "term_name"

# BM25 最低评分阈值（与 intent.recall._models 同步）
_BM25_MIN_SCORE = 0.001

# 允许的 tsvector 列名白名单（防止 SQL 注入）
_ALLOWED_TSV_COLUMNS = frozenset({"name_keywords", "name_keywords_jieba"})

# ═══════════════════════════════════════════════════════════════
# 批量召回 SQL 构建辅助函数（从 intent.recall._sql 迁移至此）
# ═══════════════════════════════════════════════════════════════


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
                                 JOIN term_relation has_term
                                   ON has_term.source_term_id = prop.term_id
                                  AND has_term.relation_category = 'HAS_TERM'
                                 JOIN term type_term
                                   ON type_term.term_id = has_term.target_term_id
                                 WHERE root.term_code = :scope_code
                                   AND root.term_type_code IN ('view', 'object')
                                   AND root.library_id = t.library_id
                                   AND t.term_type_code = type_term.term_code
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


def _group_requests_by_filter(
    requests: tuple[RecallRequest, ...],
) -> dict[frozenset[str] | None, list[RecallRequest]]:
    """按 type_filter 分组请求，同组共享一条 SQL。"""
    grouped: dict[frozenset[str] | None, list[RecallRequest]] = defaultdict(list)
    for request in requests:
        grouped[request.type_filter].append(request)
    return grouped


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


class PostgresSearchEngine(TermSearchEngine):
    """PostgreSQL 术语搜索引擎，实现 TermSearchEngine 协议。

    整合 BM25（字级/词级/分区）、子串匹配、向量搜索三路召回。
    通过 Tokenizer 协议解耦分词策略，支持中英文等多种语言。

    支持两种初始化模式：
    - 直接注入 session（调用方管理事务）
    - 注入 session_factory（engine 自行管理 session 生命周期）

    Attributes:
        _session: SQLAlchemy 数据库会话。
    """

    def __init__(
        self,
        session: Session | None = None,
        session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
    ) -> None:
        """初始化搜索引擎。

        Args:
            session: SQLAlchemy 数据库会话（调用方负责生命周期）。
            session_factory: 返回 session 上下文管理器的可调用对象。
                传入 None 且 session 也为 None 时默认使用 ``get_session``。
        """
        if session is not None:
            self._session: Session = session
            self._session_factory: Callable[[], AbstractContextManager[Session]] | None = None
        else:
            self._session_factory = session_factory if session_factory is not None else get_session
            self._session = None  # type: ignore[assignment]

    @property
    def session(self) -> Session:
        """获取当前绑定的 Session。仅在直接注入 session 时可用。"""
        if self._session is not None:
            return self._session
        raise RuntimeError(
            "PostgresSearchEngine 未绑定 session，请使用 _with_session() 上下文管理器"
        )

    def _with_session(self) -> AbstractContextManager[Session]:
        """获取 session 上下文管理器（兼容两种初始化模式）。"""
        from contextlib import nullcontext

        if self._session is not None:
            return nullcontext(self._session)
        if self._session_factory is not None:
            return self._session_factory()
        raise RuntimeError("PostgresSearchEngine 未配置 session 或 session_factory")

    # ═══════════════════════════════════════════════════════════════
    # 私有工具方法
    # ═══════════════════════════════════════════════════════════════

    def _rollback_quietly(self) -> None:
        """安全回滚会话，忽略所有异常。"""
        rollback = getattr(self._session, "rollback", None)
        if callable(rollback):
            with suppress(Exception):
                rollback()

    def _check_column_exists(self, column_name: str) -> bool:
        """检查 term_name 表中指定列是否存在（进程级缓存）。

        Args:
            column_name: 列名（如 name_keywords、name_keywords_jieba）。

        Returns:
            列是否存在。
        """
        schema = resolve_knowledge_schema()
        cache_key = f"{schema}.{column_name}"
        cached = _COLUMN_CAPS_CACHE.get(cache_key)
        if cached is not None:
            return cached

        sql = text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :table_schema "
            "AND table_name = :table_name "
            "AND column_name = :column_name "
            "LIMIT 1"
        )
        with self._with_session() as session:
            try:
                rows = session.execute(
                    sql,
                    {
                        "table_schema": schema,
                        "table_name": _TABLE,
                        "column_name": column_name,
                    },
                ).fetchall()
                _COLUMN_CAPS_CACHE[cache_key] = bool(rows)
            except Exception as exc:
                log.warning("列能力检查失败，回退为不存在: %s", exc)
                _COLUMN_CAPS_CACHE[cache_key] = False

        return bool(_COLUMN_CAPS_CACHE[cache_key])

    def _resolve_tsv_column(self, tokenizer: Tokenizer) -> str:
        """根据分词器语言选择目标 tsvector 列。

        选择策略：
        - zh_CN → name_keywords（字级 tsvector，simple 配置）
        - en_US → name_keywords_jieba（词级 tsvector），回退 name_keywords

        Args:
            tokenizer: 分词器实例。

        Returns:
            目标 tsvector 列名。
        """
        lang = tokenizer.language
        if lang == "en_US":
            # 英文优先使用词级列
            if self._check_column_exists("name_keywords_jieba"):
                return "name_keywords_jieba"
            return "name_keywords"
        # 中文（默认）使用字级列
        return "name_keywords"

    # ═══════════════════════════════════════════════════════════════
    # BM25 全文搜索
    # ═══════════════════════════════════════════════════════════════

    def search_bm25(
        self,
        *,
        query_text: str,
        top_k: int = 10,
        min_score: float = 0.01,
        tokenizer: Tokenizer,
        term_type_codes: Sequence[str] | None = None,
        partitioned: bool = False,
        per_type_limit: int = 3,
    ) -> list[BM25Result]:
        """使用 BM25 文本匹配搜索术语名称。

        Tokenizer 负责分词和 tsquery 构建，引擎负责列选择、SQL 模板和执行。

        Args:
            query_text: 查询文本（原始输入，由 tokenizer 分词后构建 tsquery）。
            top_k: 返回结果数量上限。
            min_score: 最小 BM25 分数阈值。
            tokenizer: 分词器实例（负责分词和 tsquery 构建）。
            term_type_codes: 可选术语类型白名单过滤。
            partitioned: 是否按 term_type_code 分区取 top-N。
            per_type_limit: 分区模式下每个类型的 top-N 数量。

        Returns:
            BM25Result 列表，按 score 降序。
        """
        if not query_text or not query_text.strip():
            return []

        # 1. 分词
        tokens = tokenizer.tokenize(query_text)
        if not tokens:
            return []

        # 2. 构建 tsquery（默认 AND 语义）
        tsquery = tokenizer.build_tsquery(tokens)

        # 3. 根据语言选择目标列
        tsv_column = self._resolve_tsv_column(tokenizer)

        # 4. 检查列是否存在
        if not self._check_column_exists(tsv_column):
            log.error(
                "BM25 需要 term_name.%s 列。请先执行 DDL/importer 填充此列。",
                tsv_column,
            )
            return []

        # 5. 类型过滤
        type_codes_set: set[str] | None = None
        if term_type_codes:
            type_codes_set = set(term_type_codes)

        # 6. 选择 SQL 模板并执行
        try:
            if partitioned and type_codes_set:
                return self._run_bm25_partitioned(
                    tsv_column=tsv_column,
                    tsquery=tsquery,
                    per_type_limit=per_type_limit,
                    min_score=min_score,
                    term_type_codes=type_codes_set,
                )
            return self._run_bm25_plain(
                tsv_column=tsv_column,
                tsquery=tsquery,
                top_k=top_k,
                min_score=min_score,
                term_type_codes=type_codes_set,
            )
        except Exception:
            self._rollback_quietly()
            log.exception("BM25 搜索失败")
            raise

    def _run_bm25_plain(
        self,
        *,
        tsv_column: str,
        tsquery: str,
        top_k: int,
        min_score: float,
        term_type_codes: set[str] | None = None,
    ) -> list[BM25Result]:
        """执行非分区 BM25 查询。

        Args:
            tsv_column: 已验证的 tsvector 列名。
            tsquery: PostgreSQL tsquery 字符串。
            top_k: 返回结果数量上限。
            min_score: 最小分数阈值。
            term_type_codes: 可选术语类型白名单。

        Returns:
            BM25Result 列表，按 score 降序。
        """
        if tsv_column not in _ALLOWED_TSV_COLUMNS:
            raise ValueError(f"非法的 tsvector 列名: {tsv_column}")

        type_clause: str = ""
        bindings: list[Any] = []
        if term_type_codes:
            type_clause = "\n            AND t.term_type_code IN :type_codes"
            bindings = [bindparam("type_codes", expanding=True)]

        sql_text = f"""
            SELECT
                tn.term_id,
                tn.name_text AS term_name,
                tn.name_id,
                t.term_type_code,
                ts_rank_cd(tn.{tsv_column}, query, 32) AS score,
                t.term_code
            FROM
                term_name tn,
                term t,
                to_tsquery('simple', :tsquery) query
            WHERE
                tn.{tsv_column} @@ query
                AND tn.term_id = t.term_id
                AND tn.{tsv_column} IS NOT NULL{type_clause}
            ORDER BY
                score DESC
            LIMIT :limit
        """

        sql = text(sql_text)
        if bindings:
            sql = sql.bindparams(*bindings)

        params: dict[str, Any] = {"tsquery": tsquery, "limit": top_k}
        if term_type_codes:
            params["type_codes"] = sorted(term_type_codes)

        rows = self._session.execute(sql, params).fetchall()
        return [
            BM25Result(
                term_id=str(row[0]),
                term_name=str(row[1]),
                name_id=str(row[2]),
                term_type_code=str(row[3]),
                score=float(row[4]),
                term_code=str(row[5]) if row[5] else "",
            )
            for row in rows
            if float(row[4]) >= min_score
        ]

    def _run_bm25_partitioned(
        self,
        *,
        tsv_column: str,
        tsquery: str,
        per_type_limit: int,
        min_score: float,
        term_type_codes: set[str],
    ) -> list[BM25Result]:
        """执行分区 BM25 查询（ROW_NUMBER() OVER PARTITION BY term_type_code）。

        Args:
            tsv_column: 已验证的 tsvector 列名。
            tsquery: PostgreSQL tsquery 字符串。
            per_type_limit: 每个 term_type_code 的最大结果数。
            min_score: 最小分数阈值。
            term_type_codes: 术语类型白名单（非空）。

        Returns:
            BM25Result 列表，按 score 降序。
        """
        if tsv_column not in _ALLOWED_TSV_COLUMNS:
            raise ValueError(f"非法的 tsvector 列名: {tsv_column}")

        sql_text = f"""
            SELECT term_id, term_name, name_id, term_type_code, score, term_code
            FROM (
                SELECT
                    tn.term_id,
                    tn.name_text AS term_name,
                    tn.name_id,
                    t.term_type_code,
                    ts_rank_cd(tn.{tsv_column}, query, 32) AS score,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.term_type_code
                        ORDER BY ts_rank_cd(tn.{tsv_column}, query, 32) DESC
                    ) AS rn,
                    t.term_code
                FROM
                    term_name tn,
                    term t,
                    to_tsquery('simple', :tsquery) query
                WHERE
                    tn.{tsv_column} @@ query
                    AND tn.term_id = t.term_id
                    AND tn.{tsv_column} IS NOT NULL
                    AND t.term_type_code IN :type_codes
            ) ranked
            WHERE rn <= :per_type_limit
            ORDER BY score DESC
        """
        sql = text(sql_text).bindparams(
            bindparam("type_codes", expanding=True),
        )
        params: dict[str, Any] = {
            "tsquery": tsquery,
            "type_codes": sorted(term_type_codes),
            "per_type_limit": per_type_limit,
        }
        rows = self._session.execute(sql, params).fetchall()
        return [
            BM25Result(
                term_id=str(row[0]),
                term_name=str(row[1]),
                name_id=str(row[2]),
                term_type_code=str(row[3]),
                score=float(row[4]),
                term_code=str(row[5]) if row[5] else "",
            )
            for row in rows
            if float(row[4]) >= min_score
        ]

    # ═══════════════════════════════════════════════════════════════
    # 子串匹配
    # ═══════════════════════════════════════════════════════════════

    def search_substring(
        self,
        *,
        query_text: str,
        top_k: int = 20,
        term_type_codes: Sequence[str] | None = None,
        partitioned: bool = False,
        per_type_limit: int = 3,
    ) -> list[SubstringResult]:
        """执行双向子串匹配召回。

        匹配逻辑：
        1. 术语名是查询文本的子串（term_name IN query_text）
        2. 查询文本是术语名的子串（query_text IN term_name）

        Args:
            query_text: 用户输入的查询文本。
            top_k: 最大返回数量。
            term_type_codes: 可选术语类型白名单过滤。
            partitioned: 是否按 term_type_code 分区取 top-N。
            per_type_limit: 分区模式下每个类型的 top-N 数量。

        Returns:
            SubstringResult 列表，按名称长度降序。
        """
        query_text = query_text.strip()
        if not query_text:
            return []

        type_codes_set: set[str] | None = None
        if term_type_codes:
            type_codes_set = set(term_type_codes)

        try:
            if partitioned and type_codes_set:
                return self._run_substring_partitioned(
                    query_text=query_text,
                    per_type_limit=per_type_limit,
                    term_type_codes=type_codes_set,
                )
            return self._run_substring_plain(
                query_text=query_text,
                top_k=top_k,
                term_type_codes=type_codes_set,
            )
        except Exception:
            self._rollback_quietly()
            log.exception("子串匹配召回失败: '%s'", query_text)
            raise

    def _run_substring_plain(
        self,
        *,
        query_text: str,
        top_k: int,
        term_type_codes: set[str] | None = None,
    ) -> list[SubstringResult]:
        """执行非分区子串匹配。

        Args:
            query_text: 查询文本。
            top_k: 最大返回数量。
            term_type_codes: 可选术语类型白名单。

        Returns:
            SubstringResult 列表，按名称长度降序。
        """
        if term_type_codes:
            sql = text(
                """
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
                """
            ).bindparams(
                bindparam("type_codes", expanding=True),
            )
            params: dict[str, object] = {
                "query_text": query_text,
                "type_codes": sorted(term_type_codes),
                "limit": top_k,
            }
        else:
            sql = text(
                """
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
                """
            )
            params = {"query_text": query_text, "limit": top_k}

        rows = self._session.execute(sql, params).fetchall()
        return [
            SubstringResult(
                term_id=str(row[0]),
                term_name=str(row[1]),
                name_id=str(row[2]),
                term_type_code=str(row[3]),
                score=float(len(str(row[1]))),
                term_code=str(row[4]) if row[4] else "",
            )
            for row in rows
        ]

    def _run_substring_partitioned(
        self,
        *,
        query_text: str,
        per_type_limit: int,
        term_type_codes: set[str],
    ) -> list[SubstringResult]:
        """执行分区子串匹配（ROW_NUMBER() OVER PARTITION BY term_type_code）。

        Args:
            query_text: 查询文本。
            per_type_limit: 每个 term_type_code 的最大结果数。
            term_type_codes: 术语类型白名单（非空）。

        Returns:
            SubstringResult 列表，按名称长度降序。
        """
        sql = text(
            """
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
            """
        ).bindparams(
            bindparam("type_codes", expanding=True),
        )
        params: dict[str, object] = {
            "query_text": query_text,
            "type_codes": sorted(term_type_codes),
            "per_type_limit": per_type_limit,
        }
        rows = self._session.execute(sql, params).fetchall()
        return [
            SubstringResult(
                term_id=str(row[0]),
                term_name=str(row[1]),
                name_id=str(row[2]),
                term_type_code=str(row[3]),
                score=float(len(str(row[1]))),
                term_code=str(row[4]) if row[4] else "",
            )
            for row in rows
        ]

    # ═══════════════════════════════════════════════════════════════
    # 向量语义搜索
    # ═══════════════════════════════════════════════════════════════

    def search_vector(
        self,
        *,
        query_vector: Sequence[float],
        top_k: int = 10,
        min_similarity: float = 0.5,
    ) -> list[VectorResult]:
        """使用预计算的向量进行语义搜索。

        使用 pgvector 的余弦距离算符 (<=>) 将向量与
        term_name.name_embedding 列比较，返回最相似术语。

        Args:
            query_vector: 查询文本向量（1024 维）。
            top_k: 返回结果数量上限。
            min_similarity: 最小余弦相似度阈值（0-1）。

        Returns:
            VectorResult 列表，按 similarity 降序。
        """
        vector_str = "[" + ",".join(map(str, query_vector)) + "]"

        sql = text(
            """
            SELECT
                tn.term_id,
                tn.name_text AS term_name,
                tn.name_id,
                t.term_type_code,
                1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS similarity,
                t.term_code
            FROM
                term_name tn,
                term t
            WHERE
                tn.name_embedding IS NOT NULL
                AND tn.term_id = t.term_id
            ORDER BY
                tn.name_embedding <=> CAST(:vector AS vector)
            LIMIT :limit
            """
        )

        try:
            rows = self._session.execute(sql, {"vector": vector_str, "limit": top_k}).fetchall()

            results: list[VectorResult] = []
            for row in rows:
                term_id, term_name, name_id, term_type_code, similarity, term_code = row
                if similarity >= min_similarity:
                    results.append(
                        VectorResult(
                            term_id=str(term_id),
                            term_name=str(term_name),
                            name_id=str(name_id),
                            term_type_code=str(term_type_code),
                            similarity=float(similarity),
                            term_code=str(term_code) if term_code else "",
                        )
                    )

            log.debug("向量搜索找到 %d 条结果", len(results))
            return results

        except Exception:
            log.exception("向量搜索失败")
            raise

    # ═══════════════════════════════════════════════════════════════
    # 批量召回方法（供 intent.recall 使用）
    # ═══════════════════════════════════════════════════════════════

    def search_bm25_batch(
        self,
        requests: list[RecallRequest],
        *,
        top_k: int,
        column_name: str = "name_keywords",
        tokenizer_fn: Callable[[str], str] | None = None,
        per_type_limit: int = 0,
    ) -> dict[str, list[tuple[str, str, str, str, str]]]:
        """批量 BM25 全文搜索（tsquery 窗口函数）。

        Args:
            requests: 召回请求列表。
            top_k: 单 keyword 返回数量上限。
            column_name: tsvector 列名（name_keywords / name_keywords_jieba）。
            tokenizer_fn: 将 keyword 字符串映射为 tsquery 文本的函数。
            per_type_limit: 分区模式下每个 type 的上限（0=普通模式）。

        Returns:
            ``{map_key: [(term_id, term_name, name_id, term_type_code, term_code), ...]}``。
        """
        if tokenizer_fn is None:
            raise ValueError("tokenizer_fn is required for search_bm25_batch")
        if not requests:
            return {}

        with self._with_session() as session:
            results: dict[str, list[tuple[str, str, str, str, str]]] = {}
            for type_filter, group in _group_requests_by_filter(tuple(requests)).items():
                local_per_type = per_type_limit
                if per_type_limit <= 0 and group:
                    local_per_type = group[0].per_type_limit if group[0].is_per_type else 0
                group_results = self._execute_tsquery_group(
                    session,
                    group,
                    type_filter,
                    top_k=top_k,
                    column_name=column_name,
                    tokenizer_fn=tokenizer_fn,
                    per_type_limit=local_per_type,
                )
                results.update(group_results)
            return results

    def search_substring_batch(
        self,
        requests: list[RecallRequest],
        *,
        top_k: int,
        per_type_limit: int = 0,
    ) -> dict[str, list[tuple[str, str, str, str, str]]]:
        """批量子串匹配召回。

        Args:
            requests: 召回请求列表。
            top_k: 单 keyword 返回数量上限。
            per_type_limit: 分区模式下每个 type 的上限（0=普通模式）。

        Returns:
            ``{map_key: [(term_id, term_name, name_id, term_type_code, term_code), ...]}``。
        """
        if not requests:
            return {}

        with self._with_session() as session:
            results: dict[str, list[tuple[str, str, str, str, str]]] = {}
            for type_filter, group in _group_requests_by_filter(tuple(requests)).items():
                local_per_type = per_type_limit
                if per_type_limit <= 0 and group:
                    local_per_type = group[0].per_type_limit if group[0].is_per_type else 0
                group_results = self._execute_substring_group(
                    session,
                    group,
                    type_filter,
                    top_k=top_k,
                    per_type_limit=local_per_type,
                )
                results.update(group_results)
            return results

    def search_vector_batch(
        self,
        requests: list[RecallRequest],
        *,
        top_k: int,
        per_type_limit: int = 0,
        vector_str: str | None = None,
    ) -> dict[str, list[tuple[str, str, str, str, str]]]:
        """执行单条向量召回查询（scope / type_filter / per_type 完整支持）。

        注意：向量计算仍在调用方完成（embedding service），此方法只负责 SQL 执行。

        Args:
            requests: 召回请求列表（通常只有 1 个元素，因为每条 keyword 独立执行）。
            top_k: 返回数量上限。
            per_type_limit: 分区模式下每个 type 的上限（0=普通模式）。
            vector_str: pgvector 格式的向量字符串（如 ``[0.1,0.2,...]``）。

        Returns:
            ``{map_key: [(term_id, term_name, name_id, term_type_code, term_code), ...]}``。
        """
        if not requests:
            return {}

        with self._with_session() as session:
            results: dict[str, list[tuple[str, str, str, str, str]]] = {}
            for request in requests:
                single_result = self._execute_single_vector_query(
                    session,
                    request,
                    vector_str=vector_str,
                    top_k=top_k,
                    per_type_limit=per_type_limit,
                )
                results.update(single_result)
            return results

    # ── 内部执行方法 ──────────────────────────────────────────

    def _execute_tsquery_group(
        self,
        session: Session,
        requests: list[RecallRequest],
        type_filter: frozenset[str] | None,
        *,
        top_k: int,
        column_name: str,
        tokenizer_fn: Callable[[str], str],
        per_type_limit: int = 0,
    ) -> dict[str, list[tuple[str, str, str, str, str]]]:
        """执行一组同 type_filter 的 tsquery 批量查询。"""
        scope_code = requests[0].scope_code if requests else None
        is_strict = bool(requests) and not requests[0].is_value_recall
        scope_clause = _build_effective_scope_clause(scope_code, strict=is_strict)
        input_values, params = _build_values_clause(
            requests,
            value_getter=lambda request: str(tokenizer_fn(request.keyword)),
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

    def _execute_substring_group(
        self,
        session: Session,
        requests: list[RecallRequest],
        type_filter: frozenset[str] | None,
        *,
        top_k: int,
        per_type_limit: int = 0,
    ) -> dict[str, list[tuple[str, str, str, str, str]]]:
        """执行一组同 type_filter 的子串匹配批量查询。"""
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

    def _execute_single_vector_query(
        self,
        session: Session,
        request: RecallRequest,
        *,
        vector_str: str | None = None,
        top_k: int,
        per_type_limit: int = 0,
    ) -> dict[str, list[tuple[str, str, str, str, str]]]:
        """执行一条向量召回查询（scope / type_filter / per_type 支持）。"""
        from datacloud_knowledge.retrieval.recall._models import _VECTOR_MIN_SIMILARITY

        params: dict[str, Any] = {
            "min_similarity": _VECTOR_MIN_SIMILARITY,
        }
        if vector_str is not None:
            params["vector"] = vector_str
        scope_clause = _build_effective_scope_clause(
            request.scope_code, strict=not request.is_value_recall
        )
        local_per_type = request.per_type_limit if request.is_per_type else per_type_limit
        if local_per_type > 0 and request.type_filter is not None:
            sql: Any = _build_vector_sql(
                typed=True,
                per_type=True,
                scope_clause=scope_clause,
            )
            params["type_codes"] = sorted(request.type_filter)
            params["per_type_limit"] = local_per_type
            params["limit"] = top_k * 3 * len(request.type_filter)
        elif request.type_filter is not None:
            sql = _build_vector_sql(
                typed=True,
                per_type=False,
                scope_clause=scope_clause,
            )
            params["type_codes"] = sorted(request.type_filter)
            params["limit"] = top_k * 3
        else:
            sql = _build_vector_sql(
                typed=False,
                per_type=False,
                scope_clause=scope_clause,
            )
            params["limit"] = top_k * 3
        if scope_clause:
            params.update(_build_scope_params(request.scope_code))

        rows = session.execute(sql, params).fetchall()
        results: list[tuple[str, str, str, str, str]] = []
        for term_id, term_name, name_id, term_type_code, score, term_code in rows:
            if float(score) >= _VECTOR_MIN_SIMILARITY:
                results.append(
                    (
                        str(term_id),
                        str(term_name),
                        str(name_id),
                        str(term_type_code),
                        str(term_code),
                    )
                )
        return {request.map_key: results} if results else {}

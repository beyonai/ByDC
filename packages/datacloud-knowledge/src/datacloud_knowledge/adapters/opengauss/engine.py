"""PostgreSQL 术语搜索引擎实现。

实现 TermSearchEngine 协议的三路召回策略：
- BM25: PostgreSQL tsvector + ts_rank_cd 全文搜索
- Substring: 双向子串匹配（术语名⊆查询 OR 查询⊆术语名）
- Vector: pgvector HNSW 余弦相似度搜索

通过 Tokenizer 协议解耦分词策略，支持中英文等多种语言。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from sqlalchemy import bindparam, text

from datacloud_knowledge.adapters.opengauss._db.url import resolve_knowledge_schema
from datacloud_knowledge.contracts.protocols import TermSearchEngine
from datacloud_knowledge.contracts.text import Tokenizer
from datacloud_knowledge.contracts.types import BM25Result, SubstringResult, VectorResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# 进程级列存在性缓存（减少 information_schema 重复查询）
_COLUMN_CAPS_CACHE: dict[str, bool] = {}

# term_name 表常量
_TABLE = "term_name"

# 允许的 tsvector 列名白名单（防止 SQL 注入）
_ALLOWED_TSV_COLUMNS = frozenset({"name_keywords", "name_keywords_jieba"})


class PostgresSearchEngine(TermSearchEngine):
    """PostgreSQL 术语搜索引擎，实现 TermSearchEngine 协议。

    整合 BM25（字级/词级/分区）、子串匹配、向量搜索三路召回。
    通过 Tokenizer 协议解耦分词策略，支持中英文等多种语言。

    Attributes:
        _session: SQLAlchemy 数据库会话。
    """

    def __init__(self, session: Session) -> None:
        """初始化搜索引擎。

        Args:
            session: SQLAlchemy 数据库会话。
        """
        self._session = session

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
        try:
            rows = self._session.execute(
                sql,
                {
                    "table_schema": schema,
                    "table_name": _TABLE,
                    "column_name": column_name,
                },
            ).fetchall()
            _COLUMN_CAPS_CACHE[cache_key] = bool(rows)
        except Exception as exc:
            self._rollback_quietly()
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

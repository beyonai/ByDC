"""_TermWriter Mixin — per-entity write operations for the OpenGauss adapter.

Extracted from ``writer.py`` PostgresTermWriter.
All methods use ``self.session``, ``self._now()``, ``self._new_id()`` from
``_WriterBase``. No ``__init__`` / ``__enter__`` / ``__exit__`` (provided
by ``_WriterBase``).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from sqlalchemy import delete, text

from datacloud_knowledge.adapters.opengauss._db.models import Term
from datacloud_knowledge.contracts.term_provider_types import (
    ImportResult,
    TermCreate,
    TermUpdate,
)
from datacloud_knowledge.contracts.types import TermNameCreate

from ._base import _WriterBase

log = logging.getLogger(__name__)


class _TermWriter(_WriterBase):
    """Mixin providing all term-write operations.

    Inherits session management, ID generation, and timestamp helpers from
    ``_WriterBase``. All write operations go through ``self.session``.
    """

    # Default search scope field values
    _DEFAULT_SCORE: float = 1.0
    _DEFAULT_USE_COUNT: int = 1
    _DEFAULT_CONFIRMED_COUNT: int = 1
    # User-defined term code prefix
    _TERM_CODE_PREFIX: str = "UD"

    # ═══════════════════════════════════════════════════════════════════════════════
    # TermWriter 协议方法 — 原子写入
    # ═══════════════════════════════════════════════════════════════════════════════

    def insert_term(
        self,
        *,
        term_name: str,
        term_type_code: str,
        term_code: str | None = None,
        library_id: str | None = None,
        domain_ids: list[str],
        parent_term_id: str | None = None,
        term_tags: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> str:
        """原子插入术语记录（不含知识和别名）。

        Args:
            term_name: 术语标准名称。
            term_type_code: 术语类型编码。
            term_code: 术语编码（业务唯一标识）。None 时自动生成 ``UD_xxx``。
            library_id: 术语库 ID（可选，默认为 NULL）。
            domain_ids: 所属领域 ID 列表。
            parent_term_id: 父术语 ID（可选）。
            term_tags: 术语标签属性（JSONB，可选）。
            user_id: 创建用户 ID（可选，当前仅用于日志）。

        Returns:
            生成的 term_id（UUID v4）。
        """
        now = self._now()
        term_id = self._new_id()
        db_term_code = term_code if term_code is not None else self._generate_term_code()

        self.session.execute(
            text(
                "INSERT INTO term "
                "(term_id, term_code, term_name, term_type_code, library_id, "
                "domain_ids, parent_term_id, term_tags, created_time, updated_time) "
                "VALUES ("
                ":term_id, :term_code, :term_name, :term_type_code, :library_id, "
                ":domain_ids, :parent_term_id, CAST(:term_tags AS jsonb), :now, :now"
                ")"
            ),
            {
                "term_id": term_id,
                "term_code": db_term_code,
                "term_name": term_name,
                "term_type_code": term_type_code,
                "library_id": library_id,
                "domain_ids": domain_ids,
                "parent_term_id": parent_term_id,
                "term_tags": json.dumps(term_tags) if term_tags else "{}",
                "now": now,
            },
        )

        log.info(
            "创建术语: term_id=%s term_code=%s term_name=%s user_id=%s",
            term_id,
            db_term_code,
            term_name,
            user_id,
        )
        return term_id

    def insert_term_knowledge(
        self,
        *,
        term_id: str,
        desc_summary: str,
        desc: str,
    ) -> str:
        """原子插入术语知识记录。

        Args:
            term_id: 归属术语 ID。
            desc_summary: 知识摘要。
            desc: 知识原文。

        Returns:
            生成的 knowledge_id（UUID v4）。
        """
        knowledge_id = self._new_id()
        now = self._now()
        self.session.execute(
            text(
                "INSERT INTO term_knowledge "
                '(knowledge_id, term_id, desc_summary, "desc", created_time, updated_time) '
                "VALUES (:knowledge_id, :term_id, :desc_summary, :desc, :now, :now)"
            ),
            {
                "knowledge_id": knowledge_id,
                "term_id": term_id,
                "desc_summary": desc_summary,
                "desc": desc,
                "now": now,
            },
        )
        log.info("创建术语关联知识: knowledge_id=%s -> term_id=%s", knowledge_id, term_id)
        return knowledge_id

    def create_term_name(
        self,
        *,
        term_id: str,
        name_text: str,
        search_scope: dict[str, object],
        user_id: str | None = None,
    ) -> str:
        """创建用户级术语别名（幂等）。

        先检查同 term_id + name_text + scope_user_id 组合是否已存在，
        存在则返回已有 name_id，否则 INSERT 新记录并返回新 name_id。

        Args:
            term_id: 归属术语 ID。
            name_text: 别名文本。
            search_scope: 搜索作用域（JSONB 格式，含 scope_user_id/score/use_count 等）。
            user_id: 创建用户 ID，用于重复检查时提取 scope_user_id。

        Returns:
            生成的或已存在的 name_id。
        """
        scope_user_id = self._resolve_scope_user_id(search_scope, user_id)

        existing_row = self.session.execute(
            text(
                "SELECT name_id FROM term_name "
                "WHERE term_id = :term_id AND name_text = :name_text "
                "AND COALESCE((search_scope->>'scope_user_id'), '') = :user_id "
                "ORDER BY updated_time DESC LIMIT 1"
            ),
            {
                "term_id": term_id,
                "name_text": name_text,
                "user_id": scope_user_id,
            },
        ).fetchone()

        if existing_row is not None:
            existing_name_id = str(existing_row[0])
            log.info(
                "用户术语别名已存在: %s -> %s (user=%s, name_id=%s)",
                name_text,
                term_id,
                scope_user_id,
                existing_name_id,
            )
            return existing_name_id

        now = self._now()
        merged_scope = self._build_insert_scope(search_scope, scope_user_id, now.isoformat())

        name_id = self._new_id()
        self.session.execute(
            text(
                "INSERT INTO term_name "
                "(name_id, term_id, name_text, search_scope, created_time, updated_time) "
                "VALUES (:name_id, :term_id, :name_text, CAST(:search_scope AS jsonb), :now, :now)"
            ),
            {
                "name_id": name_id,
                "term_id": term_id,
                "name_text": name_text,
                "search_scope": json.dumps(merged_scope),
                "now": now,
            },
        )
        log.info(
            "创建用户术语别名: %s -> %s (user=%s, name_id=%s)",
            name_text,
            term_id,
            scope_user_id,
            name_id,
        )
        return name_id

    def batch_create_term_names(self, *, items: Sequence[TermNameCreate]) -> list[str]:
        """批量创建术语别名。

        逐个调用 create_term_name()，保持幂等语义：每个 item 独立检查重复。

        Args:
            items: 别名创建项序列。

        Returns:
            生成的 name_id 列表，与 items 顺序对应。
        """
        return [
            self.create_term_name(
                term_id=item.term_id,
                name_text=item.name_text,
                search_scope=item.search_scope,
                user_id=item.user_id,
            )
            for item in items
        ]

    def create_term_with_knowledge(
        self,
        *,
        term_name: str,
        term_type_code: str,
        library_id: str | None = None,
        domain_ids: list[str],
        knowledge_desc: str | None = None,
        parent_term_id: str | None = None,
        term_tags: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> str:
        """创建新术语及其关联知识（级联写入，委托原子方法）。

        .. deprecated::
            新代码应直接使用 :meth:`insert_term` + :meth:`insert_term_knowledge`
            + :meth:`create_term_name` 编排。

        执行流程：insert_term → insert_term_knowledge → create_term_name。
        三步在同一 Session 内完成，由调用方控制事务提交。
        """
        term_id = self.insert_term(
            term_name=term_name,
            term_type_code=term_type_code,
            library_id=library_id,
            domain_ids=domain_ids,
            parent_term_id=parent_term_id,
            term_tags=term_tags,
            user_id=user_id,
        )

        if knowledge_desc:
            self.insert_term_knowledge(
                term_id=term_id,
                desc_summary=knowledge_desc[:200],
                desc=knowledge_desc,
            )

        now = self._now()
        name_search_scope: dict[str, object] = {}
        if user_id:
            name_search_scope = {
                "scope_user_id": user_id,
                "score": self._DEFAULT_SCORE,
                "use_count": self._DEFAULT_USE_COUNT,
                "confirmed_count": self._DEFAULT_CONFIRMED_COUNT,
                "last_used_at": now.isoformat(),
            }
        self.create_term_name(
            term_id=term_id,
            name_text=term_name,
            search_scope=name_search_scope,
            user_id=user_id,
        )

        log.info(
            "创建术语及知识: term_id=%s term_name=%s user_id=%s",
            term_id,
            term_name,
            user_id,
        )
        return term_id

    def create_term_knowledge_record(
        self,
        *,
        term_id: str,
        desc_summary: str,
        desc: str,
    ) -> str:
        """为已有术语创建关联知识记录。

        与 create_term_with_knowledge 不同，本方法假设术语已存在，仅创建
        TermKnowledge 记录。

        Args:
            term_id: 归属术语 ID。
            desc_summary: 知识摘要。
            desc: 知识原文。

        Returns:
            生成的 knowledge_id。
        """
        knowledge_id = self._new_id()
        now = self._now()
        self.session.execute(
            text(
                "INSERT INTO term_knowledge "
                '(knowledge_id, term_id, desc_summary, "desc", created_time, updated_time) '
                "VALUES (:knowledge_id, :term_id, :desc_summary, :desc, :now, :now)"
            ),
            {
                "knowledge_id": knowledge_id,
                "term_id": term_id,
                "desc_summary": desc_summary,
                "desc": desc,
                "now": now,
            },
        )
        log.info("创建术语关联知识: %s -> %s", knowledge_id, term_id)
        return knowledge_id

    def batch_create_vocabulary(self, *, words: Sequence[str]) -> None:
        """批量写入分词词典（幂等去重）。

        使用 PostgreSQL unnest + WHERE NOT EXISTS 避免重复插入。
        TermVocabulary 表为 jieba 自定义词典数据源。

        Args:
            words: 词汇文本序列。
        """
        if not words:
            return

        word_list = list(words)
        self.session.execute(
            text(
                "INSERT INTO term_vocabulary (word) "
                "SELECT w.word FROM unnest(CAST(:words AS text[])) AS w(word) "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM term_vocabulary tv WHERE tv.word = w.word"
                ")"
            ),
            {"words": word_list},
        )

    def get_name_search_scope(self, *, name_id: str) -> dict[str, object] | None:
        """读取 term_name 记录上的 search_scope JSONB 字段。"""
        row = self.session.execute(
            text("SELECT search_scope FROM term_name WHERE name_id = :name_id"),
            {"name_id": name_id},
        ).fetchone()
        if row is None or row[0] is None:
            return None
        if isinstance(row[0], dict):
            return dict(row[0])

        try:
            parsed = json.loads(str(row[0]))
        except (json.JSONDecodeError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def update_name_search_scope(
        self,
        *,
        name_id: str,
        search_scope: dict[str, object],
        updated_time: object,
    ) -> None:
        """原子更新 term_name 的 search_scope 和 updated_time。"""
        self.session.execute(
            text(
                "UPDATE term_name "
                "SET search_scope = CAST(:search_scope AS jsonb), updated_time = :updated_time "
                "WHERE name_id = :name_id"
            ),
            {
                "name_id": name_id,
                "search_scope": json.dumps(search_scope),
                "updated_time": updated_time,
            },
        )

    # ── TermProvider 协议新增方法 ──────────────────────────────────────

    def import_terms(
        self,
        *,
        dataset_id: str,
        terms: list[TermCreate],
    ) -> ImportResult:
        """批量新增术语（含同义词、标签、扩展属性）。

        对每条 TermCreate，依次执行 insert_term + create_term_name。
        所有操作在同一个 Session 内完成，由调用方控制事务提交。

        Args:
            dataset_id: 目标术语库 ID（映射到 library_id）。
            terms: 待新增术语列表。

        Returns:
            ImportResult，含创建数和 term_id 列表。
        """
        created = 0
        term_ids: list[str] = []
        errors: list[str] = []

        for term in terms:
            try:
                term_id = self.insert_term(
                    term_name=term.term_name,
                    term_type_code=term.term_type,
                    term_code=term.term_code if term.term_code else None,
                    library_id=dataset_id,
                    domain_ids=[],
                    parent_term_id=term.parent_term_code or None,
                    term_tags=dict(term.labels),
                )

                # 创建标准名称记录
                if term.term_name:
                    self.create_term_name(
                        term_id=term_id,
                        name_text=term.term_name,
                        search_scope={},
                    )

                # 创建同义词记录
                for syn in term.synonyms:
                    if syn and syn != term.term_name:
                        self.create_term_name(
                            term_id=term_id,
                            name_text=syn,
                            search_scope={},
                        )

                term_ids.append(term_id)
                created += 1
            except Exception as exc:
                log.exception(
                    "import_terms 单条创建失败: term_name=%s",
                    term.term_name,
                )
                errors.append(f"{term.term_name}: {exc}")

        log.info(
            "import_terms 完成: dataset_id=%s created=%d errors=%d",
            dataset_id,
            created,
            len(errors),
        )
        return ImportResult(created=created, term_ids=term_ids, errors=errors)

    def upsert_term(
        self,
        *,
        term_code: str,
        term_name: str,
        term_type_code: str,
        library_id: str | None = None,
        domain_ids: list[str] | None = None,
        search_scope: dict[str, object] | None = None,
        backfill_vectors: bool = True,
    ) -> str:
        """UPSERT 单个术语（按 term_code + term_type_code），含 term_name 和向量回填。

        写入流程：
        1. UPSERT term 行（有则 UPDATE，无则 INSERT）
        2. UPSERT term_name 行（幂等）
        3. 提交事务
        4. 回填 tsvector（best-effort，失败不抛）
        5. 回填 embedding（best-effort，30s 超时）
        """
        now = self._now()
        domains = domain_ids or []
        scope = search_scope or {}

        # ── 1. UPSERT term ───────────────────────────────────────────
        # 有 library_id 时按三元组 (library_id, term_type_code, term_code) 幂等；
        # 无 library_id 时退回二元组 (term_type_code, term_code)，保持向后兼容。
        if library_id is not None:
            existing = self.session.execute(
                text(
                    "SELECT term_id FROM term "
                    "WHERE library_id = :library_id "
                    "AND term_code = :code AND term_type_code = :type "
                    "AND parent_term_id IS NULL"
                ),
                {"library_id": library_id, "code": term_code, "type": term_type_code},
            ).fetchone()
        else:
            existing = self.session.execute(
                text(
                    "SELECT term_id, library_id FROM term "
                    "WHERE term_code = :code AND term_type_code = :type AND parent_term_id IS NULL"
                ),
                {"code": term_code, "type": term_type_code},
            ).fetchone()

        if existing is not None:
            term_id = str(existing[0])
            # UPDATE 现有行（不覆盖 library_id，除非调用方显式传入）
            set_parts: dict[str, object] = {
                "term_name": term_name,
                "domain_ids": domains,
                "updated_time": now,
            }
            if library_id is not None:
                set_parts["library_id"] = library_id
            set_clause = ", ".join(f"{key} = :{key}" for key in set_parts)
            params: dict[str, object] = dict(set_parts)
            params["term_id"] = term_id
            self.session.execute(
                text(f"UPDATE term SET {set_clause} WHERE term_id = :term_id"),
                params,
            )
            log.info("upsert_term UPDATE: term_id=%s code=%s", term_id, term_code)
        else:
            term_id = self._new_id()
            db_library_id = library_id
            self.session.execute(
                text(
                    "INSERT INTO term "
                    "(term_id, term_code, term_name, term_type_code, library_id, "
                    "domain_ids, parent_term_id, term_tags, created_time, updated_time) "
                    "VALUES ("
                    ":term_id, :term_code, :term_name, :term_type_code, :library_id, "
                    ":domain_ids, NULL, :term_tags, :now, :now"
                    ")"
                ),
                {
                    "term_id": term_id,
                    "term_code": term_code,
                    "term_name": term_name,
                    "term_type_code": term_type_code,
                    "library_id": db_library_id,
                    "domain_ids": domains,
                    "term_tags": "{}",
                    "now": now,
                },
            )
            log.info(
                "upsert_term INSERT: term_id=%s code=%s",
                term_id,
                term_code,
            )

        # ── 2. UPSERT term_name ──────────────────────────────────────
        self.create_term_name(
            term_id=term_id,
            name_text=term_name,
            search_scope=scope,
        )

        # ── 3. 向量回填（best-effort，非阻塞） ─────────────────────────
        if backfill_vectors:
            self._backfill_vectors_optional(term_id=term_id)

        return term_id

    def _backfill_vectors_optional(self, *, term_id: str) -> None:
        """tsvector + embedding 回填（best-effort，失败不抛，超时 30s）。"""
        import threading

        result_holder: dict[str, object] = {}
        error_holder: dict[str, Exception] = {}

        def _run() -> None:
            try:
                from datacloud_knowledge.adapters import backfill_embeddings

                backfill_embeddings(term_ids=[term_id])
                result_holder["ok"] = True
            except Exception as exc:
                error_holder["exc"] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=30.0)

        if thread.is_alive():
            log.warning(
                "upsert_term 向量回填超时（30s），term_id=%s 请稍后手动执行: "
                "datacloud-knowledge backfill-embeddings --term-ids %s",
                term_id,
                term_id,
            )
        elif "exc" in error_holder:
            log.warning(
                "upsert_term 向量回填失败: %s，term_id=%s",
                error_holder["exc"],
                term_id,
            )
        else:
            log.debug("upsert_term 向量回填完成: term_id=%s", term_id)

    # ── 批量 UPSERT（单 SQL，替代逐条 upsert_term）────────────────────

    def bulk_upsert_terms_no_library(
        self,
        *,
        terms: list[tuple[str, str, str]],
        #     (term_code, term_name, term_type_code)
    ) -> list[str]:
        """批量 UPSERT term 行（无 library_id 场景）。

        1 次 SELECT 分组 → executemany INSERT 新行 → executemany UPDATE 旧行。
        """
        if not terms:
            return []

        now = self._now()
        conn = self.session.connection().connection

        codes = [t[0] for t in terms]
        types_list = [t[2] for t in terms]

        # ── 1. Single SELECT to find existing ──
        existing_rows = conn.execute(
            """SELECT term_code, term_type_code, term_id
               FROM term
               WHERE term_type_code = ANY(%(types)s)
                 AND term_code = ANY(%(codes)s)
                 AND parent_term_id IS NULL""",
            {"types": types_list, "codes": codes},
        ).fetchall()
        existing_map = {(r[0], r[1]): str(r[2]) for r in existing_rows}

        # ── 2. Group new vs existing ──
        insert_data: list[tuple[str, str, str, str]] = []  # (tid, code, name, type)
        update_data: list[tuple[str, str, str]] = []  # (name, code, ttype)
        term_ids: list[str] = []

        for term_code, term_name, term_type_code in terms:
            key = (term_code, term_type_code)
            if key in existing_map:
                tid = existing_map[key]
                term_ids.append(tid)
                if term_name:
                    update_data.append((term_name, term_code, term_type_code))
            else:
                tid = self._new_id()
                term_ids.append(tid)
                insert_data.append((tid, term_code, term_name, term_type_code))

        # ── 3. Batch INSERT ──
        if insert_data:
            cur = conn.cursor()
            cur.executemany(
                """INSERT INTO term (
                       term_id, term_code, term_name, term_type_code,
                       domain_ids, parent_term_id, term_tags, created_time, updated_time
                   ) VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s)""",
                [
                    (tid, code, name, ttype, "{}", "{}", now, now)
                    for tid, code, name, ttype in insert_data
                ],
            )

        # ── 4. Batch UPDATE ──
        if update_data:
            cur = conn.cursor()
            cur.executemany(
                """UPDATE term SET term_name = %s, updated_time = %s
                   WHERE term_code = %s AND term_type_code = %s
                     AND parent_term_id IS NULL""",
                [(name, now, code, ttype) for name, code, ttype in update_data],
            )

        return term_ids

    def bulk_create_term_names_no_scope(
        self,
        *,
        items: list[tuple[str, str]],
        #     (term_id, name_text)
    ) -> None:
        """批量创建 term_name，幂等跳过已存在。用 executemany。"""
        if not items:
            return

        now = self._now()
        conn = self.session.connection().connection

        # Check which already exist
        tids = [i[0] for i in items]
        names = [i[1] for i in items]
        existing_rows = conn.execute(
            """SELECT term_id, name_text FROM term_name
               WHERE term_id = ANY(%(tids)s)
                 AND name_text = ANY(%(names)s)
                 AND search_scope = '{}'::jsonb""",
            {"tids": tids, "names": names},
        ).fetchall()
        existing_set = {(r[0], r[1]) for r in existing_rows}

        new_items: list[tuple[str, str, str, str, object, object]] = []
        seen: set[tuple[str, str]] = set()
        for tid, name in items:
            if (tid, name) not in existing_set and (tid, name) not in seen:
                seen.add((tid, name))
                new_items.append((self._new_id(), tid, name, "{}", now, now))

        if new_items:
            try:
                cur = conn.cursor()
                cur.executemany(
                    """INSERT INTO term_name (
                           name_id, term_id, name_text, search_scope,
                           created_time, updated_time
                       ) VALUES (%s, %s, %s, %s, %s, %s)""",
                    new_items,
                )
            except Exception:
                # 并发/残存数据导致的偶发唯一约束冲突，忽略
                log.debug(
                    "bulk_create_term_names_no_scope: unique violation ignored (already exists)"
                )

        log.info("bulk_create_term_names_no_scope: %d new / %d total", len(new_items), len(items))

    def update_term(
        self,
        *,
        dataset_id: str,
        term_id: str,
        updates: TermUpdate,
    ) -> None:
        """更新术语。仅更新非 None 字段。

        Args:
            dataset_id: 术语库 ID（OpenGauss 不按此过滤，仅用于接口兼容）。
            term_id: 术语 ID。
            updates: 更新字段（None = 不修改）。

        Raises:
            ValueError: 术语不存在。
        """
        _ = dataset_id  # OpenGauss 不按 dataset_id 过滤
        now = self._now()

        # 先检查术语是否存在
        existing = self.session.execute(
            text("SELECT term_id FROM term WHERE term_id = :term_id"),
            {"term_id": term_id},
        ).fetchone()

        if existing is None:
            raise ValueError(f"术语不存在: {term_id}")

        # 构建 UPDATE SET 子句
        set_parts: dict[str, object] = {}
        if updates.term_name is not None:
            set_parts["term_name"] = updates.term_name
        if updates.term_code is not None:
            set_parts["term_code"] = updates.term_code
        if updates.term_type is not None:
            set_parts["term_type_code"] = updates.term_type
        if updates.parent_term_code is not None:
            set_parts["parent_term_id"] = updates.parent_term_code
        if updates.desc is not None:
            set_parts["desc_summary"] = updates.desc
        if updates.labels is not None:
            set_parts["term_tags"] = json.dumps(updates.labels)
        if updates.domain_ids is not None:
            set_parts["domain_ids"] = updates.domain_ids
        # ext_attrs 暂存到 desc_summary 补充字段（OpenGauss 无独立 ext_attrs 列）
        if updates.ext_attrs is not None:
            ext_json = json.dumps(updates.ext_attrs)
            self.session.execute(
                text(
                    "UPDATE term SET desc_summary = COALESCE(desc_summary, '') || :ext "
                    "WHERE term_id = :term_id"
                ),
                {"ext": f" ext_attrs:{ext_json}", "term_id": term_id},
            )

        if not set_parts:
            return

        set_parts["updated_time"] = now

        # 构建动态 UPDATE SQL
        set_clause = ", ".join(f"{key} = :{key}" for key in set_parts)
        params: dict[str, object] = dict(set_parts)
        params["term_id"] = term_id

        self.session.execute(
            text(f"UPDATE term SET {set_clause} WHERE term_id = :term_id"),
            params,
        )

        # 更新同义词（TermName 表）：删除旧同义词，插入新同义词
        if updates.synonyms is not None:
            # 删除旧的非标准名同义词
            self.session.execute(
                text(
                    "DELETE FROM term_name WHERE term_id = :term_id AND search_scope = '{}'::jsonb"
                ),
                {"term_id": term_id},
            )
            # 插入新同义词
            for syn in updates.synonyms:
                if syn.strip():
                    self.create_term_name(
                        term_id=term_id,
                        name_text=syn.strip(),
                        search_scope={},
                    )

        log.info(
            "update_term 完成: term_id=%s fields=%s",
            term_id,
            list(set_parts.keys()),
        )

    # ═══════════════════════════════════════════════════════════════════════════════
    # 内部辅助方法
    # ═══════════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _resolve_scope_user_id(
        search_scope: dict[str, object],
        user_id: str | None,
    ) -> str:
        """从 search_scope 或 user_id 参数中提取 scope_user_id。

        优先使用 search_scope 中的 scope_user_id，其次使用 user_id 参数，
        均无则返回空字符串。
        """
        scope_uid = search_scope.get("scope_user_id")
        if scope_uid is not None:
            return str(scope_uid)
        if user_id is not None:
            return user_id
        return ""

    @staticmethod
    def _build_insert_scope(
        search_scope: dict[str, object],
        scope_user_id: str,
        now_iso: str,
    ) -> dict[str, object]:
        """构建插入用的 search_scope 字典，补齐缺失的默认字段。

        以调用方传入的 search_scope 为基础，确保 scope_user_id 已设置，
        对未提供的 score/use_count/confirmed_count/last_used_at 填充默认值。

        Args:
            search_scope: 调用方传入的搜索作用域。
            scope_user_id: 已解析的用户标识。
            now_iso: ISO 格式时间戳，由调用方统一提供以保持时间一致性。

        Returns:
            补齐后的 search_scope 字典（新字典，不修改入参）。
        """
        defaults: dict[str, object] = {
            "scope_user_id": scope_user_id,
            "score": _TermWriter._DEFAULT_SCORE,
            "use_count": _TermWriter._DEFAULT_USE_COUNT,
            "confirmed_count": _TermWriter._DEFAULT_CONFIRMED_COUNT,
            "last_used_at": now_iso,
        }
        # 调用方提供的值优先，默认值作为兜底
        merged: dict[str, object] = dict(defaults)
        merged.update(search_scope)
        # 确保 scope_user_id 不被调用方覆盖为空
        merged["scope_user_id"] = scope_user_id
        return merged

    @staticmethod
    def _generate_term_code() -> str:
        """生成全局唯一的 term_code。

        格式：UD_{32位hex}，UD 前缀表示 User Defined。
        """
        return f"{_TermWriter._TERM_CODE_PREFIX}_{_WriterBase._new_id().replace('-', '')}"

    def delete_term(self, *, term_id: str) -> None:
        """Delete a term by ID."""
        self.session.execute(delete(Term).where(Term.term_id == term_id))

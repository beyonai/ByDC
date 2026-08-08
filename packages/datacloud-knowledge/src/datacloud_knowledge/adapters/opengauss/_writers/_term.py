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
from typing import Any

from sqlalchemy import select, text

from datacloud_knowledge.adapters.opengauss._db.models import (
    TermDomain,
    TermType,
)
from datacloud_knowledge.contracts.term_provider_types import (
    ImportResult,
    TermUpdate,
)
from datacloud_knowledge.contracts.types import TermNameCreate

from ._base import _WriterBase

log = logging.getLogger(__name__)


def _raise_missing_cascade_owner(relation_code: str) -> None:
    raise ValueError(f"cascade relation owner must exist: {relation_code}")


def _raise_multiple_cascade_owners(relation_code: str) -> None:
    raise ValueError(f"cascade relation has multiple owners: {relation_code}")


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
        ext_attrs: dict[str, object] | None = None,
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
            ext_attrs: 自定义扩展属性（JSONB，可选）。
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
                "domain_ids, parent_term_id, term_tags, ext_attrs, created_time, updated_time) "
                "VALUES ("
                ":term_id, :term_code, :term_name, :term_type_code, :library_id, "
                ":domain_ids, :parent_term_id, CAST(:term_tags AS jsonb), "
                "CAST(:ext_attrs AS jsonb), :now, :now"
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
                "ext_attrs": json.dumps(ext_attrs) if ext_attrs else "{}",
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

    def update_term_co_occurrence(self, *, term_id: str, patch: dict[str, int]) -> None:
        """更新 term_tags.co_occurrence（计数版伙伴集合）。

        独立新写路径：
        - 已存在伙伴 key 计数累加、新伙伴 key 插入
        - Top-50 固定上限：合并后按 count 降序取前 50（自然衰减近似）
        - 读改写 + SELECT ... FOR UPDATE 行级锁（Spec 备选方案）

        **实现取舍**：首选原地拼接 ``jsonb_object_agg`` /
        ``jsonb || jsonb`` 在 OpenGauss 2.x **不存在**（实测
        ``jsonb_object_agg(text, numeric) does not exist``、``operator does
        not exist: jsonb || jsonb``），故采用备选读改写 + FOR UPDATE：
        - SELECT term_tags FOR UPDATE 锁行（行级原子，无并发读改写竞态）
        - Python 合并（计数累加 + Top-50 裁剪）
        - UPDATE 整体写回（保留 term_tags 其他 key，如 kb 元数据）

        **禁止经 update_term**：其 ext_attrs 分支把 ext_attrs 拼入
        desc_summary（"OpenGauss 无独立 ext_attrs 列"的遗留怪癖）、term_tags
        整列替换——本方法为独立 SQL 写路径。

        Args:
            term_id: 归属 term_id。
            patch: ``{partner_term_id: count}`` 增量。
        """
        if not patch:
            return
        row = self.session.execute(
            text("SELECT term_tags FROM term WHERE term_id = :term_id FOR UPDATE"),
            {"term_id": term_id},
        ).fetchone()
        tags = dict(row[0]) if row is not None and row[0] else {}
        if not isinstance(tags, dict):
            tags = {}
        co = tags.get("co_occurrence")
        if not isinstance(co, dict):
            co = {}
        merged: dict[str, int] = {}
        for key, value in co.items():
            try:
                merged[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        for key, value in patch.items():
            merged[str(key)] = merged.get(str(key), 0) + int(value)
        top50 = dict(sorted(merged.items(), key=lambda item: (-item[1], item[0]))[:50])
        tags["co_occurrence"] = top50
        self.session.execute(
            text("UPDATE term SET term_tags = :tags WHERE term_id = :term_id"),
            {"term_id": term_id, "tags": json.dumps(tags, ensure_ascii=False)},
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
        library_id: str,
        terms: list[dict[str, Any]],
    ) -> ImportResult:
        """Comprehensive 5-stage batch term import.

        Stage 0: validate libraryId exists (gate before transaction)
        Stage 1: in-memory dedup/merge/conflict resolution
        Stage 2: domain code→id resolution + batch upsert term_types
        Stage 3: batch insert terms + synonyms
        Stage 4: batch insert relations + stub term creation
        Stage 5: return summary

        All DB writes (stages 2-4) happen in a single transaction.

        Args:
            library_id: Target library ID.
            terms: List of term dicts. Each dict may contain:
                - term_name (required)
                - term_code (optional)
                - term_type_code / termTypeCode / term_type
                - parent_term_code / parentTermCode
                - desc_summary / descSummary / desc
                - synonyms / synonymList (list of str)
                - labels / tags / term_tags (dict)
                - domain_ids / domainIds (list of domain IDs)
                - domain_codes / domainCodes (list of domain codes)
                - relations (list of relation dicts with source/target/name/category)

        Returns:
            Dict with: library_id, created, updated, skipped, term_ids, errors, summary.
        """
        now = self._now()

        # ── Stage 0: validate input ────────────────────────────────────
        # library_id is NOT validated against term_library — it may not
        # exist yet (terms can be imported before the library is created).
        # The library_id is simply stored in the term.library_id column.

        if not terms:
            return ImportResult(created=0, updated=0, skipped=0, term_ids=[], errors=[])

        # ── Normalize: accept both dict and TermCreate dataclass ────────
        terms = self._normalize_terms(terms)

        # ── Stage 1: in-memory dedup/merge/conflict resolution ─────────
        merged_terms, dedup_log = self._dedup_and_merge_terms(terms)

        # ── Stage 2: domain code→id resolution + batch upsert term_types
        domain_code_to_id = self._resolve_import_domain_codes(library_id, merged_terms)
        type_codes = self._extract_term_type_codes(merged_terms)
        self._batch_upsert_term_types(library_id, type_codes, now)

        # ── Stage 3: batch insert terms + synonyms ──────────────────────
        import_stats = self._batch_insert_import_terms(
            library_id, merged_terms, domain_code_to_id, now
        )

        # ── Stage 4: batch insert relations + stub term creation ────────
        relation_stats = self._batch_insert_import_relations(
            library_id, merged_terms, domain_code_to_id, now
        )

        # ── Stage 5: return summary ─────────────────────────────────────
        errors: list[str] = []
        if dedup_log:
            errors.append(f"Dedup: {dedup_log}")
        if import_stats["errors"]:
            errors.extend(import_stats["errors"])
        if relation_stats["errors"]:
            errors.extend(relation_stats["errors"])

        summary_parts = [
            f"Terms created={import_stats['created']} updated={import_stats['updated']} "
            f"skipped={import_stats['skipped']}",
            f"Relations created={relation_stats['created']} "
            f"stubs={relation_stats['stubs_created']} skipped={relation_stats['skipped']}",
        ]
        if dedup_log:
            summary_parts.insert(0, dedup_log)

        log.info(
            "import_terms complete: library_id=%s created=%d updated=%d "
            "skipped=%d relations=%d stubs=%d errors=%d",
            library_id,
            import_stats["created"],
            import_stats["updated"],
            import_stats["skipped"],
            relation_stats["created"],
            relation_stats["stubs_created"],
            len(errors),
        )

        return ImportResult(
            created=import_stats["created"],
            updated=import_stats["updated"],
            skipped=import_stats["skipped"],
            term_ids=import_stats["term_ids"],
            errors=errors,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # import_terms internal stages
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _normalize_terms(terms: list[Any]) -> list[dict[str, Any]]:
        """Convert dataclass terms to dict for downstream .get() access.

        Accepts ``list[dict]`` (no-op) or ``list[TermCreate]`` (converted via
        ``dataclasses.asdict``).
        """
        from dataclasses import asdict, is_dataclass

        if not terms:
            return []
        first = terms[0]
        if isinstance(first, dict):
            return terms
        if is_dataclass(first) and not isinstance(first, type):
            return [asdict(t) for t in terms]
        return terms

    def _dedup_and_merge_terms(
        self, terms: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], str]:
        """Stage 1: in-memory dedup/merge/conflict resolution.

        Strategy:
        - Vote on term_type_code (majority wins when multiple records for same term_name)
        - Merge termCodes (first non-empty wins, suffix duplicates with _dupN)
        - Merge synonyms across duplicates
        - Merge labels/tags across duplicates
        """
        from collections import Counter, defaultdict

        by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for t in terms:
            name = (t.get("term_name") or t.get("termName") or "").strip()
            if name:
                by_name[name].append(t)

        merged: list[dict[str, Any]] = []
        dedup_count = 0

        for name, group in by_name.items():
            if len(group) == 1:
                merged.append(group[0])
                continue

            dedup_count += len(group) - 1
            # Vote on term_type_code
            type_votes: Counter[str] = Counter()
            for t in group:
                tc = t.get("term_type_code") or t.get("termTypeCode") or t.get("term_type")
                if tc:
                    type_votes[tc] += 1
            best_type = type_votes.most_common(1)[0][0] if type_votes else "concept"

            # Merge termCodes
            all_codes: list[str] = []
            for t in group:
                code = t.get("term_code") or t.get("termCode") or ""
                if code and code not in all_codes:
                    all_codes.append(code)

            # Merge synonyms
            all_syns: list[str] = []
            for t in group:
                syns = t.get("synonyms") or t.get("synonymList") or []
                for s in syns:
                    if s and s not in all_syns and s != name:
                        all_syns.append(s)

            # Merge labels
            merged_labels: dict[str, Any] = {}
            for t in group:
                labels = t.get("labels") or t.get("tags") or t.get("term_tags") or {}
                merged_labels.update(labels)

            # Merge ext_attrs
            merged_ext_attrs: dict[str, Any] = {}
            for t in group:
                ext_a = t.get("ext_attrs") or t.get("extAttrs") or {}
                if isinstance(ext_a, dict):
                    merged_ext_attrs.update(ext_a)

            # Merge domain info
            domain_ids: list[str] = []
            domain_codes: list[str] = []
            for t in group:
                domain_ids.extend(t.get("domain_ids") or t.get("domainIds") or [])
                domain_codes.extend(t.get("domain_codes") or t.get("domainCodes") or [])
                # Also extract codes from domain: [{code, name}] format
                domain_objs = t.get("domain") or []
                if isinstance(domain_objs, list):
                    for dobj in domain_objs:
                        if isinstance(dobj, dict):
                            dcode = dobj.get("code") or dobj.get("domain_code") or ""
                            if dcode:
                                domain_codes.append(str(dcode))

            base = group[0].copy()
            base["term_type_code"] = best_type
            base["term_code"] = all_codes[0] if all_codes else ""
            base["synonyms"] = all_syns
            base["labels"] = merged_labels
            base["ext_attrs"] = merged_ext_attrs
            base["domain_ids"] = domain_ids
            base["domain_codes"] = domain_codes

            # Suffix additional codes
            for i, code in enumerate(all_codes[1:], start=2):
                suffix = f"_dup{i}"
                dup = base.copy()
                dup["term_code"] = code
                dup["term_name"] = f"{name}{suffix}"
                merged.append(dup)

            merged.append(base)

        log_msg = f"{dedup_count} duplicates merged" if dedup_count else ""
        return merged, log_msg

    def _extract_term_type_codes(self, terms: list[dict[str, Any]]) -> set[str]:
        """Extract unique term_type_codes from import terms."""
        codes: set[str] = set()
        for t in terms:
            tc = t.get("term_type_code") or t.get("termTypeCode") or t.get("term_type")
            if tc and tc != "-1":
                codes.add(tc)
        return codes

    def _resolve_import_domain_codes(
        self, library_id: str, terms: list[dict[str, Any]]
    ) -> dict[str, str]:
        """Resolve all domain_codes to domain_ids for the import batch."""
        all_domain_codes: set[str] = set()
        for t in terms:
            codes = t.get("domain_codes") or t.get("domainCodes") or []
            for c in codes:
                if c:
                    all_domain_codes.add(str(c))

        if not all_domain_codes:
            return {}

        rows = self.session.execute(
            select(TermDomain.domain_code, TermDomain.domain_id).where(
                TermDomain.library_id == library_id,
                TermDomain.domain_code.in_(list(all_domain_codes)),
            )
        ).all()
        return {str(r[0]): str(r[1]) for r in rows}

    def _batch_upsert_term_types(self, library_id: str, type_codes: set[str], now: Any) -> None:
        """Batch upsert term_type rows for the import."""
        if not type_codes:
            return

        # Find existing types
        existing = (
            self.session.execute(
                select(TermType.type_code).where(
                    TermType.library_id == library_id,
                    TermType.type_code.in_(list(type_codes)),
                )
            )
            .scalars()
            .all()
        )
        existing_set = set(existing)

        # Insert missing types
        for tc in type_codes:
            if tc not in existing_set:
                self.session.execute(
                    text(
                        "INSERT INTO term_type "
                        "(type_code, type_name, type_desc, type_category, "
                        "is_builtin, library_id, domain_ids, created_time, updated_time) "
                        "VALUES (:code, :name, :desc, :cat, :builtin, :lid, :dids, :now, :now)"
                    ),
                    {
                        "code": tc,
                        "name": tc,
                        "desc": f"Auto-created via import to {library_id}",
                        "cat": 0,
                        "builtin": False,
                        "lid": library_id,
                        "dids": [],
                        "now": now,
                    },
                )
        log.debug(
            "_batch_upsert_term_types: %d existing, %d new for library %s",
            len(existing_set),
            len(type_codes - existing_set),
            library_id,
        )

    def _batch_insert_import_terms(
        self,
        library_id: str,
        terms: list[dict[str, Any]],
        domain_code_to_id: dict[str, str],
        now: Any,
    ) -> dict[str, Any]:
        """Stage 3: batch insert terms + synonyms.

        Returns stats dict with created, updated, skipped, term_ids,
        name_changed_ids (only terms with new/changed names), errors.
        """
        created = 0
        updated = 0
        skipped = 0
        term_ids: list[str] = []
        name_changed_ids: list[str] = []  # only terms that need backfill
        errors: list[str] = []

        for t in terms:
            try:
                term_name = (t.get("term_name") or t.get("termName") or "").strip()
                if not term_name:
                    skipped += 1
                    errors.append(f"term_name is required for term {t}")
                    continue

                term_code = t.get("term_code") or t.get("termCode") or ""
                if not term_code:
                    term_code = self._generate_term_code()

                term_type_code = (
                    t.get("term_type_code") or t.get("termTypeCode") or t.get("term_type")
                )

                if not term_type_code:
                    skipped += 1
                    errors.append(f"term_type_code is required for term {term_name}")
                    continue
                parent_term_code = t.get("parent_term_code") or t.get("parentTermCode") or ""
                parent_term_id: str | None = None
                if parent_term_code:
                    parent_row = self.session.execute(
                        text(
                            "SELECT term_id FROM term "
                            "WHERE term_code = :code AND library_id = :lid AND term_type_code = :type_code "
                            "LIMIT 1"
                        ),
                        {"code": parent_term_code, "lid": library_id, "type_code": term_type_code},
                    ).fetchone()
                    if parent_row:
                        parent_term_id = str(parent_row[0])

                desc_summary = t.get("desc_summary") or t.get("descSummary") or t.get("desc") or ""

                # Resolve domain IDs
                domain_ids: list[str] = []
                dids = t.get("domain_ids") or t.get("domainIds") or []
                dcodes = t.get("domain_codes") or t.get("domainCodes") or []

                # Also support domain: [{code, name}] format — extract codes
                domain_objs = t.get("domain") or []
                if isinstance(domain_objs, list):
                    for dobj in domain_objs:
                        if isinstance(dobj, dict):
                            dcode = dobj.get("code") or dobj.get("domain_code") or ""
                            if dcode:
                                dcodes.append(str(dcode))

                for did in dids:
                    if did and str(did) not in domain_ids:
                        domain_ids.append(str(did))
                for dcode in dcodes:
                    resolved = domain_code_to_id.get(str(dcode))
                    if resolved and resolved not in domain_ids:
                        domain_ids.append(resolved)

                # Merge labels/tags
                labels = t.get("labels") or t.get("tags") or t.get("term_tags") or {}
                term_tags = labels if isinstance(labels, dict) else {}
                # Merge ext_attrs
                ext_attrs = t.get("ext_attrs") or t.get("extAttrs") or {}
                ext_attrs = ext_attrs if isinstance(ext_attrs, dict) else {}

                # Check for existing term → stub upgrade
                existing = self.session.execute(
                    text(
                        "SELECT term_id, term_name, term_type_code FROM term "
                        "WHERE term_code = :code AND library_id = :lid AND term_type_code = :type_code "
                        "LIMIT 1"
                    ),
                    {"code": term_code, "lid": library_id, "type_code": term_type_code},
                ).fetchone()

                if existing is not None:
                    # Stub upgrade: update the stub with real data
                    existing_term_id = str(existing[0])
                    existing_name = str(existing[1]) if existing[1] else ""
                    self.session.execute(
                        text(
                            "UPDATE term SET "
                            "term_name = :name, term_type_code = :type_code, "
                            "desc_summary = :desc, domain_ids = :dids, "
                            "term_tags = CAST(:tags AS jsonb), "
                            "ext_attrs = CAST(:ext_attrs AS jsonb), "
                            "parent_term_id = :parent_id, "
                            "updated_time = :now "
                            "WHERE term_id = :tid"
                        ),
                        {
                            "name": term_name,
                            "type_code": term_type_code,
                            "desc": desc_summary if desc_summary else None,
                            "dids": domain_ids,
                            "tags": json.dumps(term_tags),
                            "ext_attrs": json.dumps(ext_attrs),
                            "parent_id": parent_term_id,
                            "now": now,
                            "tid": existing_term_id,
                        },
                    )
                    term_ids.append(existing_term_id)
                    updated += 1
                    # Stub upgrade always needs backfill (stub may not have had term_names)
                    name_changed = term_name != existing_name
                    if name_changed:
                        name_changed_ids.append(existing_term_id)
                        log.debug(
                            "_batch_insert: stub upgrade name changed: %r → %r (term_id=%s)",
                            existing_name,
                            term_name,
                            existing_term_id,
                        )
                    else:
                        log.debug(
                            "_batch_insert: stub upgrade name unchanged: %r (term_id=%s)",
                            term_name,
                            existing_term_id,
                        )
                    log.info("Stub upgraded: term_id=%s term_code=%s", existing_term_id, term_code)
                else:
                    # Regular insert or upsert by (term_code, library_id)
                    # existing_non_stub = self.session.execute(
                    #     text(
                    #         "SELECT term_id, term_name FROM term "
                    #         "WHERE term_code = :code AND library_id = :lid "
                    #         "LIMIT 1"
                    #     ),
                    #     {"code": term_code, "lid": library_id},
                    # ).fetchone()

                    # if existing_non_stub is not None:
                    #     # Update existing
                    #     existing_tid = str(existing_non_stub[0])
                    #     existing_name = str(existing_non_stub[1]) if existing_non_stub[1] else ""
                    #     self.session.execute(
                    #         text(
                    #             "UPDATE term SET "
                    #             "term_name = :name, term_type_code = :type_code, "
                    #             "desc_summary = :desc, domain_ids = :dids, "
                    #             "term_tags = CAST(:tags AS jsonb), "
                    #             "ext_attrs = CAST(:ext_attrs AS jsonb), "
                    #             "parent_term_id = :parent_id, "
                    #             "updated_time = :now "
                    #             "WHERE term_id = :tid"
                    #         ),
                    #         {
                    #             "name": term_name,
                    #             "type_code": term_type_code,
                    #             "desc": desc_summary if desc_summary else None,
                    #             "dids": domain_ids,
                    #             "tags": json.dumps(term_tags),
                    #             "ext_attrs": json.dumps(ext_attrs),
                    #             "parent_id": parent_term_id,
                    #             "now": now,
                    #             "tid": existing_tid,
                    #         },
                    #     )
                    #     term_ids.append(existing_tid)
                    #     updated += 1
                    #     if term_name != existing_name:
                    #         name_changed_ids.append(existing_tid)
                    #         log.debug(
                    #             "_batch_insert: update name changed: %r → %r (term_id=%s)",
                    #             existing_name,
                    #             term_name,
                    #             existing_tid,
                    #         )
                    #     else:
                    #         log.debug(
                    #             "_batch_insert: update name unchanged: %r (term_id=%s), skip backfill",
                    #             term_name,
                    #             existing_tid,
                    #         )
                    # else:
                    # Insert new
                    term_id = self._new_id()
                    self.session.execute(
                        text(
                            "INSERT INTO term "
                            "(term_id, term_code, term_name, term_type_code, library_id, "
                            "domain_ids, parent_term_id, term_tags, ext_attrs, "
                            "created_time, updated_time) "
                            "VALUES ("
                            ":tid, :code, :name, :type_code, :lid, "
                            ":dids, :parent_id, CAST(:tags AS jsonb), "
                            "CAST(:ext_attrs AS jsonb), :now, :now"
                            ")"
                        ),
                        {
                            "tid": term_id,
                            "code": term_code,
                            "name": term_name,
                            "type_code": term_type_code,
                            "lid": library_id,
                            "dids": domain_ids,
                            "parent_id": parent_term_id,
                            "tags": json.dumps(term_tags),
                            "ext_attrs": json.dumps(ext_attrs),
                            "now": now,
                        },
                    )
                    term_ids.append(term_id)
                    created += 1
                    name_changed_ids.append(term_id)
                    log.debug(
                        "_batch_insert: new term created term_id=%s name=%r",
                        term_id,
                        term_name,
                    )
                # Insert standard name as term_name (for keyword/jieba/vector lookup)
                name_id = self.create_term_name(
                    term_id=term_ids[-1],
                    name_text=term_name,
                    search_scope={},
                )
                log.warning(
                    "[IMPORT] created term_name name_id=%s for term_id=%s name=%r",
                    name_id,
                    term_ids[-1],
                    term_name,
                )

                # Insert synonyms as term_names
                syns = t.get("synonyms") or t.get("synonymList") or []
                for syn in syns:
                    if syn and syn.strip() and syn.strip() != term_name:
                        self.create_term_name(
                            term_id=term_ids[-1],
                            name_text=syn.strip(),
                            search_scope={},
                        )

            except Exception as exc:
                msg = f"{t.get('term_name', 'unknown')}: {exc}"
                log.exception("import_terms term insert failed: %s", msg)
                errors.append(msg)
                skipped += 1

        log.warning(
            "_batch_insert_import_terms done: created=%d updated=%d skipped=%d "
            "name_changed=%d errors=%d",
            created,
            updated,
            skipped,
            len(name_changed_ids),
            len(errors),
        )
        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "term_ids": term_ids,
            "name_changed_ids": name_changed_ids,
            "errors": errors,
        }

    def _batch_insert_import_relations(
        self,
        library_id: str,
        terms: list[dict[str, Any]],
        domain_code_to_id: dict[str, str],
        now: Any,
    ) -> dict[str, Any]:
        """Stage 4: batch insert relations + stub term creation.

        For each relation, resolves source/target term references.
        Creates stub terms for referenced terms that don't exist yet.
        """
        import_created = 0
        stubs_created = 0
        skipped: int = 0
        errors: list[str] = []

        for t in terms:
            relations = t.get("related_to") or t.get("relatedTo") or t.get("relations") or []
            if not relations:
                continue

            source_term_name = (t.get("term_name") or t.get("termName") or "").strip()
            if not source_term_name:
                continue

            # Resolve source term_id
            source_term_code = t.get("term_code") or t.get("termCode") or ""
            source_term_id: str | None = None
            if source_term_code:
                row = self.session.execute(
                    text(
                        "SELECT term_id FROM term "
                        "WHERE term_code = :code AND library_id = :lid "
                        "LIMIT 1"
                    ),
                    {"code": source_term_code, "lid": library_id},
                ).fetchone()
                if row:
                    source_term_id = str(row[0])

            if source_term_id is None:
                skipped += len(relations)
                continue

            for rel in relations:
                try:
                    target_code = (
                        rel.get("term_code")
                        or rel.get("termCode")
                        or rel.get("target_term_code")
                        or rel.get("targetTermCode")
                        or ""
                    )
                    target_name = (
                        rel.get("term_name")
                        or rel.get("termName")
                        or rel.get("target_term_name")
                        or rel.get("targetTermName")
                        or ""
                    )
                    rel_name = rel.get("relation_name") or rel.get("relationName") or "relates_to"
                    rel_category = (
                        rel.get("relation_category") or rel.get("relationCategory") or "BUSINESS"
                    )
                    relation_code = str(rel.get("relation_code") or rel.get("relationCode") or "")
                    cascade_delete = rel.get("cascade_delete") is True

                    if not target_code and not target_name:
                        skipped += 1
                        continue

                    # Resolve target term
                    target_term_id: str | None = None
                    if target_code:
                        row = self.session.execute(
                            text(
                                "SELECT term_id FROM term "
                                "WHERE term_code = :code AND library_id = :lid "
                                "LIMIT 1"
                            ),
                            {"code": target_code, "lid": library_id},
                        ).fetchone()
                        if row:
                            target_term_id = str(row[0])

                    # Create stub if not found
                    if target_term_id is None and target_name and not cascade_delete:
                        stub_code = target_code or f"STUB_{self._new_id().replace('-', '')[:12]}"
                        stub_type = rel.get("term_type_code") or rel.get("termTypeCode") or "_stub"
                        target_term_id = self._new_id()
                        self.session.execute(
                            text(
                                "INSERT INTO term "
                                "(term_id, term_code, term_name, term_type_code, library_id, "
                                "domain_ids, parent_term_id, term_tags, ext_attrs, "
                                "created_time, updated_time) "
                                "VALUES ("
                                ":tid, :code, :name, :type_code, :lid, "
                                "'{}', NULL, '{}'::jsonb, '{}'::jsonb, :now, :now"
                                ")"
                            ),
                            {
                                "tid": target_term_id,
                                "code": stub_code,
                                "name": target_name,
                                "type_code": stub_type,
                                "lid": library_id,
                                "now": now,
                            },
                        )
                        stubs_created += 1

                    if target_term_id is None:
                        if cascade_delete:
                            _raise_missing_cascade_owner(relation_code)
                        skipped += 1
                        continue

                    if cascade_delete and relation_code:
                        other_owner = self.session.execute(
                            text(
                                "SELECT target_term_id FROM term_relation "
                                "WHERE source_term_id = :src "
                                "AND ext_attrs->>'relation_code' = :rcode "
                                "AND target_term_id <> :tgt LIMIT 1"
                            ),
                            {
                                "src": source_term_id,
                                "rcode": relation_code,
                                "tgt": target_term_id,
                            },
                        ).scalar_one_or_none()
                        if other_owner is not None:
                            _raise_multiple_cascade_owners(relation_code)

                    # Insert relation (check duplicate first)
                    relation_identity_clause = (
                        "AND ext_attrs->>'relation_code' = :rcode "
                        if relation_code
                        else "AND relation_name = :rname "
                    )
                    existing_rel = self.session.execute(
                        text(
                            "SELECT 1 FROM term_relation "
                            "WHERE source_term_id = :src AND target_term_id = :tgt "
                            f"{relation_identity_clause}"
                            "LIMIT 1"
                        ),
                        {
                            "src": source_term_id,
                            "tgt": target_term_id,
                            "rname": rel_name,
                            "rcode": relation_code,
                        },
                    ).scalar_one_or_none()

                    if existing_rel is None:
                        relation_id = self._new_id()
                        self.session.execute(
                            text(
                                "INSERT INTO term_relation "
                                "(relation_id, source_term_id, target_term_id, "
                                "relation_name, relation_category, cardinality, "
                                "ext_attrs, created_time, updated_time) "
                                "VALUES ("
                                ":rid, :src, :tgt, :rname, :rcat, :card, "
                                "CAST(:ext_attrs AS jsonb), :now, :now"
                                ")"
                            ),
                            {
                                "rid": relation_id,
                                "src": source_term_id,
                                "tgt": target_term_id,
                                "rname": rel_name,
                                "rcat": rel_category,
                                "card": rel.get("cardinality") or "1:1",
                                "ext_attrs": json.dumps(
                                    {
                                        "relation_code": relation_code,
                                        "relation_version": 1,
                                    }
                                    if relation_code
                                    else {}
                                ),
                                "now": now,
                            },
                        )
                        import_created += 1
                    else:
                        skipped += 1

                except Exception as exc:
                    errors.append(f"relation {rel.get('relation_name', '?')}: {exc}")
                    skipped += 1

        return {
            "created": import_created,
            "stubs_created": stubs_created,
            "skipped": skipped,
            "errors": errors,
        }

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

        # ── 3. 向量回填（best-effort） ─────────────────────────
        if backfill_vectors:
            self.session.commit()
            self.session.begin()
            self._backfill_jieba_tsvector([term_id])
            self._backfill_vectors_async([term_id])

        return term_id

    def _backfill_vectors_async(self, term_ids: list[str]) -> None:
        """异步回填 name_keywords + name_embedding（独立连接，线程安全）。

        best-effort，失败不抛，超时 60s。
        """
        import threading

        log.warning("[BACKFILL-async] starting thread for term_ids=%s", term_ids)
        result_holder: dict[str, object] = {}
        error_holder: dict[str, Exception] = {}

        def _run() -> None:
            try:
                from datacloud_knowledge.adapters import backfill_embeddings, backfill_tsvector

                # 1. name_keywords (simple tsvector) — idempotent whole-table
                log.warning("[BACKFILL-async] running backfill_tsvector...")
                ts_result = backfill_tsvector(force=False)
                log.warning("[BACKFILL-async] backfill_tsvector done: %s", ts_result)

                # 2. name_embedding (pgvector) — targeted by term_ids
                log.warning(
                    "[BACKFILL-async] running backfill_embeddings for %d term_ids...",
                    len(term_ids),
                )
                emb_result = backfill_embeddings(term_ids=term_ids)
                log.warning("[BACKFILL-async] backfill_embeddings done: %s", emb_result)

                result_holder["ok"] = True
            except Exception as exc:
                log.exception("_backfill_vectors_async: exception in thread")
                error_holder["exc"] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=60.0)

        if thread.is_alive():
            log.warning("[BACKFILL-async] TIMEOUT (60s), term_ids=%s", term_ids)
        elif "exc" in error_holder:
            log.warning("[BACKFILL-async] FAILED: %s, term_ids=%s", error_holder["exc"], term_ids)
        else:
            log.warning(
                "[BACKFILL-async] done: %d terms (name_keywords + embedding)", len(term_ids)
            )

    def _backfill_jieba_tsvector(self, term_ids: list[str]) -> int:
        """为指定 term_ids 的 term_name 行回填 name_keywords_jieba 列。

        使用 self.session 查询 + exec_driver_sql 更新。
        Returns: 更新的行数。
        """
        return _backfill_jieba_tsvector_with_conn(self.session.connection(), term_ids)

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
        """Delete a term with cascade.

        Checks for child terms (409), then deletes in order:
        term_relation (source/target), term_name, term_knowledge, then the term row.

        Args:
            term_id: The term's primary key.

        Raises:
            ValueError: If child terms exist (409 conflict).
        """
        # Check for children → 409
        children_count = int(
            self.session.execute(
                text("SELECT COUNT(*) FROM term WHERE parent_term_id = :tid"),
                {"tid": term_id},
            ).scalar_one()
        )
        if children_count > 0:
            raise ValueError(
                f"Cannot delete term '{term_id}': {children_count} child term(s) exist"
            )

        # Delete term_relation where this term is source or target
        self.session.execute(
            text("DELETE FROM term_relation WHERE source_term_id = :tid OR target_term_id = :tid"),
            {"tid": term_id},
        )

        # Delete term_name rows
        self.session.execute(
            text("DELETE FROM term_name WHERE term_id = :tid"),
            {"tid": term_id},
        )

        # Delete term_knowledge rows
        self.session.execute(
            text("DELETE FROM term_knowledge WHERE term_id = :tid"),
            {"tid": term_id},
        )

        # Delete the term row
        result = self.session.execute(
            text("DELETE FROM term WHERE term_id = :tid"),
            {"tid": term_id},
        )
        rowcount: int = result.rowcount  # type: ignore[attr-defined]

        if rowcount == 0:
            log.warning("delete_term: term_id=%s not found", term_id)
        else:
            log.info("delete_term: term_id=%s deleted=%d", term_id, rowcount)


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level backfill helpers (independent connections, safe outside sessions)
# ═══════════════════════════════════════════════════════════════════════════════


def _backfill_jieba_tsvector_with_conn(conn: Any, term_ids: list[str]) -> int:
    """回填 name_keywords_jieba，使用给定的 SQLAlchemy Connection。

    conn 必须来自已提交事务的连接，确保能看到 term_name 行。
    """
    import jieba

    rows = conn.execute(
        text(
            "SELECT tn.name_id, tn.name_text FROM term_name tn "
            "WHERE tn.term_id = ANY(:tids) AND tn.name_text IS NOT NULL "
            "AND tn.name_keywords_jieba IS NULL"
        ),
        {"tids": term_ids},
    ).all()

    if not rows:
        log.warning("[BACKFILL-jieba] NO rows found for term_ids=%s", term_ids)
        return 0

    log.warning("[BACKFILL-jieba] found %d rows with NULL name_keywords_jieba", len(rows))

    jieba_batch: list[tuple[str, str]] = []
    for name_id, name_text in rows:
        tokens = [t for t in jieba.lcut_for_search(str(name_text)) if t.strip()]
        if tokens:
            jieba_batch.append((str(name_id), " ".join(tokens)))

    if not jieba_batch:
        log.warning("[BACKFILL-jieba] no valid tokens after jieba processing")
        return 0

    log.warning("[BACKFILL-jieba] updating %d rows", len(jieba_batch))
    updated = 0
    page_size = 500
    for i in range(0, len(jieba_batch), page_size):
        chunk = jieba_batch[i : i + page_size]
        single_row = "(%s::varchar, %s::text)"
        values_clause = ",".join([single_row] * len(chunk))
        flat: list[str] = []
        for nid, jt in chunk:
            flat.extend([nid, jt])
        result = conn.exec_driver_sql(
            "UPDATE term_name tn SET name_keywords_jieba = to_tsvector('simple', v.jt) "
            f"FROM (VALUES {values_clause}) AS v(id, jt) WHERE tn.name_id = v.id",
            tuple(flat),
        )
        conn.commit()
        updated += result.rowcount

    log.warning("[BACKFILL-jieba] done, total updated=%d", updated)
    return updated


def run_import_backfill(term_ids: list[str]) -> None:
    """导入后统一回填三列（name_keywords + name_keywords_jieba + name_embedding）。

    使用独立连接，可在 writer session 关闭后安全调用。
    """
    import threading

    if not term_ids:
        return

    log.warning("[BACKFILL] starting for %d term_ids", len(term_ids))

    # 1. jieba tsvector — uses independent psycopg connection
    try:
        import psycopg

        from datacloud_knowledge.adapters.opengauss._db.url import (
            build_postgres_connection_uri,
            resolve_knowledge_schema_for_connection,
        )

        schema = resolve_knowledge_schema_for_connection()
        uri = build_postgres_connection_uri(schema=schema)
        with psycopg.connect(uri, autocommit=True) as raw_conn, raw_conn.cursor() as cur:
            rows = cur.execute(
                "SELECT tn.name_id, tn.name_text FROM term_name tn "
                "WHERE tn.term_id = ANY(%s) AND tn.name_text IS NOT NULL "
                "AND tn.name_keywords_jieba IS NULL",
                (term_ids,),
            ).fetchall()

            if rows:
                import jieba

                jieba_batch: list[tuple[str, str]] = []
                for name_id, name_text in rows:
                    tokens = [t for t in jieba.lcut_for_search(str(name_text)) if t.strip()]
                    if tokens:
                        jieba_batch.append((str(name_id), " ".join(tokens)))

                if jieba_batch:
                    updated = 0
                    page_size = 500
                    for i in range(0, len(jieba_batch), page_size):
                        chunk = jieba_batch[i : i + page_size]
                        single_row = "(%s::varchar, %s::text)"
                        values_clause = ",".join([single_row] * len(chunk))
                        flat: list[str] = []
                        for nid, jt in chunk:
                            flat.extend([nid, jt])
                        cur.execute(
                            "UPDATE term_name tn SET name_keywords_jieba = "
                            "to_tsvector('simple', v.jt) "
                            f"FROM (VALUES {values_clause}) AS v(id, jt) "
                            "WHERE tn.name_id = v.id",
                            flat,
                        )
                        updated += cur.rowcount
                    log.warning("[BACKFILL] jieba done, updated=%d", updated)
                else:
                    log.warning("[BACKFILL] jieba: no valid tokens")
            else:
                log.warning("[BACKFILL] jieba: no NULL rows found")
    except Exception:
        log.exception("[BACKFILL] jieba failed")

    # 2. name_keywords + name_embedding (async thread, independent connections)
    def _async_backfill() -> None:
        try:
            from datacloud_knowledge.adapters import backfill_embeddings, backfill_tsvector

            ts_result = backfill_tsvector(force=False)
            log.warning("[BACKFILL] tsvector done: %s", ts_result)
            emb_result = backfill_embeddings(term_ids=term_ids)
            log.warning("[BACKFILL] embeddings done: %s", emb_result)
        except Exception:
            log.exception("[BACKFILL] async failed")

    thread = threading.Thread(target=_async_backfill, daemon=True)
    thread.start()
    thread.join(timeout=60.0)
    if thread.is_alive():
        log.warning("[BACKFILL] async TIMEOUT (60s)")
    else:
        log.warning("[BACKFILL] all done for %d term_ids", len(term_ids))

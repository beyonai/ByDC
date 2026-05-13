"""术语写入器 — PostgresTermWriter 实现 TermWriter 协议。

从 storage.py 重构提取写入逻辑，封装为有状态类，遵从 api/protocols.py 中 TermWriter 协议。
调用方通过构造函数注入 SQLAlchemy Session，负责事务边界管理（commit/rollback）。
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from datacloud_knowledge.adapters.opengauss._db.connection import get_session
from datacloud_knowledge.contracts.types import TermNameCreate

log = logging.getLogger(__name__)

# 默认搜索作用域字段值
_DEFAULT_SCORE = 1.0
_DEFAULT_USE_COUNT = 1
_DEFAULT_CONFIRMED_COUNT = 1
# 用户自定义术语编码前缀
_TERM_CODE_PREFIX = "UD"


class PostgresTermWriter:
    """PostgreSQL 术语写入器，实现 TermWriter 协议。

    所有写入操作通过构造函数注入的 SQLAlchemy Session 执行，
    不自行管理事务边界。幂等性保证：create_term_name 重复调用
    返回已有 ID 而非重复插入。

    支持两种初始化模式：
    - 直接注入 session（调用方管理事务）
    - 注入 session_factory（writer 自行管理 session 生命周期）
    """

    def __init__(
        self,
        session: Session | None = None,
        session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
    ) -> None:
        """初始化写入器。

        Args:
            session: SQLAlchemy ORM Session，由调用方管理生命周期。
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
        """获取当前 Session（context manager 内使用）。"""
        if self._session is not None:
            return self._session
        raise RuntimeError(
            "PostgresTermWriter 未绑定 session，请在 context manager 内使用 "
            "或构造时传入 session 参数"
        )

    def _get_session_ctx(self) -> AbstractContextManager[Session]:
        """获取 session 上下文管理器。"""
        if self._session is not None:
            from contextlib import nullcontext

            return nullcontext(self._session)
        if self._session_factory is not None:
            return self._session_factory()
        raise RuntimeError("PostgresTermWriter 未配置 session 或 session_factory")

    # ═══════════════════════════════════════════════════════════════════════════════
    # TermWriter 协议方法 — 原子写入
    # ═══════════════════════════════════════════════════════════════════════════════

    # --- create_term_name, batch_create_term_names (see below) ---

    def insert_term(
        self,
        *,
        term_name: str,
        term_type_code: str,
        library_id: str | None = None,
        domain_id: str,
        parent_term_id: str | None = None,
        term_tags: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> str:
        """原子插入术语记录（不含知识和别名）。

        Args:
            term_name: 术语标准名称。
            term_type_code: 术语类型编码。
            library_id: 术语库 ID（可选，默认为 NULL）。
            domain_id: 所属领域 ID。
            parent_term_id: 父术语 ID（可选）。
            term_tags: 术语标签属性（JSONB，可选）。
            user_id: 创建用户 ID（可选，当前仅用于日志）。

        Returns:
            生成的 term_id（UUID v4）。
        """
        now = datetime.now(tz=UTC)
        term_id = str(uuid.uuid4())
        term_code = self._generate_term_code()

        self._session.execute(
            text(
                "INSERT INTO term "
                "(term_id, term_code, term_name, term_type_code, library_id, "
                "domain_id, parent_term_id, term_tags, created_time, updated_time) "
                "VALUES ("
                ":term_id, :term_code, :term_name, :term_type_code, :library_id, "
                ":domain_id, :parent_term_id, CAST(:term_tags AS jsonb), :now, :now"
                ")"
            ),
            {
                "term_id": term_id,
                "term_code": term_code,
                "term_name": term_name,
                "term_type_code": term_type_code,
                "library_id": library_id,
                "domain_id": domain_id,
                "parent_term_id": parent_term_id,
                "term_tags": json.dumps(term_tags) if term_tags else None,
                "now": now,
            },
        )

        log.info(
            "创建术语: term_id=%s term_code=%s term_name=%s user_id=%s",
            term_id,
            term_code,
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
        knowledge_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)
        self._session.execute(
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

        existing_row = self._session.execute(
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

        merged_scope = self._build_insert_scope(search_scope, scope_user_id)

        name_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)
        self._session.execute(
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

    # --- create_term_with_knowledge (deprecated, delegates to atomic methods) ---

    def create_term_with_knowledge(
        self,
        *,
        term_name: str,
        term_type_code: str,
        library_id: str | None = None,
        domain_id: str,
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
        # 使用原子方法，避免重复 INSERT 逻辑
        term_id = self.insert_term(
            term_name=term_name,
            term_type_code=term_type_code,
            library_id=library_id,
            domain_id=domain_id,
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

        now = datetime.now(tz=UTC)
        name_search_scope: dict[str, object] = {}
        if user_id:
            name_search_scope = {
                "scope_user_id": user_id,
                "score": _DEFAULT_SCORE,
                "use_count": _DEFAULT_USE_COUNT,
                "confirmed_count": _DEFAULT_CONFIRMED_COUNT,
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
        knowledge_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)
        self._session.execute(
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
        self._session.execute(
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
        row = self._session.execute(
            text("SELECT search_scope FROM term_name WHERE name_id = :name_id"),
            {"name_id": name_id},
        ).fetchone()
        if row is None or row[0] is None:
            return None
        if isinstance(row[0], dict):
            return dict(row[0])
        import json as _json

        try:
            parsed = _json.loads(str(row[0]))
        except (_json.JSONDecodeError, TypeError):
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
        import json as _json

        self._session.execute(
            text(
                "UPDATE term_name "
                "SET search_scope = CAST(:search_scope AS jsonb), updated_time = :updated_time "
                "WHERE name_id = :name_id"
            ),
            {
                "name_id": name_id,
                "search_scope": _json.dumps(search_scope),
                "updated_time": updated_time,
            },
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
    ) -> dict[str, object]:
        """构建插入用的 search_scope 字典，补齐缺失的默认字段。

        以调用方传入的 search_scope 为基础，确保 scope_user_id 已设置，
        对未提供的 score/use_count/confirmed_count/last_used_at 填充默认值。

        Args:
            search_scope: 调用方传入的搜索作用域。
            scope_user_id: 已解析的用户标识。

        Returns:
            补齐后的 search_scope 字典（新字典，不修改入参）。
        """
        now_iso = datetime.now(tz=UTC).isoformat()
        defaults: dict[str, object] = {
            "scope_user_id": scope_user_id,
            "score": _DEFAULT_SCORE,
            "use_count": _DEFAULT_USE_COUNT,
            "confirmed_count": _DEFAULT_CONFIRMED_COUNT,
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
        return f"{_TERM_CODE_PREFIX}_{uuid.uuid4().hex}"

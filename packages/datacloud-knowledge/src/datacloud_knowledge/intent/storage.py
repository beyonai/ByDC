"""追问存储写入 — 算法 D 存储部分。"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

log = logging.getLogger(__name__)


def create_user_term_name(
    name_text: str,
    term_id: str,
    user_id: str,
    session: Any,
) -> str:
    """Create a user-scoped TermName record.

    Args:
        name_text: The alias text.
        term_id: The term this alias maps to.
        user_id: The user who owns this alias.
        session: SQLAlchemy Session.

    Returns:
        The generated name_id.
    """
    existing_row = session.execute(
        text(
            "SELECT name_id FROM term_name "
            "WHERE term_id = :term_id AND name_text = :name_text "
            "AND COALESCE((search_scope->>'scope_user_id'), '') = :user_id "
            "ORDER BY updated_time DESC LIMIT 1"
        ),
        {
            "term_id": term_id,
            "name_text": name_text,
            "user_id": user_id,
        },
    ).fetchone()
    if existing_row is not None:
        existing_name_id = str(existing_row[0])
        log.info(
            "User term name already exists: %s -> %s (user=%s, name_id=%s)",
            name_text,
            term_id,
            user_id,
            existing_name_id,
        )
        return existing_name_id

    name_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    search_scope = {
        "scope_user_id": user_id,
        "score": 1.0,
        "use_count": 1,
        "confirmed_count": 1,
        "last_used_at": now.isoformat(),
    }

    session.execute(
        text(
            "INSERT INTO term_name "
            "(name_id, term_id, name_text, search_scope, created_time, updated_time) "
            "VALUES (:name_id, :term_id, :name_text, CAST(:search_scope AS jsonb), :now, :now)"
        ),
        {
            "name_id": name_id,
            "term_id": term_id,
            "name_text": name_text,
            "search_scope": json.dumps(search_scope),
            "now": now,
        },
    )
    log.info("Created user term name: %s -> %s (user=%s)", name_text, term_id, user_id)
    return name_id


def create_term_with_knowledge(
    term_code: str,
    term_name: str,
    term_type_code: str,
    domain_id: str,
    knowledge_text: str,
    user_id: str,
    session: Any,
) -> tuple[str, str, str]:  # ← 改返回类型
    """Create a new Term with associated TermKnowledge and user-scoped TermName.
    Returns:
        (term_id, knowledge_id, name_id)  # ← 增加 name_id
    """
    term_id = str(uuid.uuid4())
    term_now = datetime.now(tz=UTC)
    session.execute(
        text(
            "INSERT INTO term "
            "(term_id, term_code, term_name, term_type_code, domain_id, created_time, updated_time) "
            "VALUES ("
            ":term_id, :term_code, :term_name, :term_type_code, :domain_id, :now, :now"
            ")"
        ),
        {
            "term_id": term_id,
            "term_code": term_code,
            "term_name": term_name,
            "term_type_code": term_type_code,
            "domain_id": domain_id,
            "now": term_now,
        },
    )
    knowledge_id = str(uuid.uuid4())
    knowledge_now = datetime.now(tz=UTC)
    session.execute(
        text(
            "INSERT INTO term_knowledge "
            '(knowledge_id, term_id, desc_summary, "desc", created_time, updated_time) '
            "VALUES (:knowledge_id, :term_id, :desc_summary, :desc, :now, :now)"
        ),
        {
            "knowledge_id": knowledge_id,
            "term_id": term_id,
            "desc_summary": knowledge_text[:200],
            "desc": knowledge_text,
            "now": knowledge_now,
        },
    )
    name_id = create_user_term_name(term_name, term_id, user_id, session)  # ← 获取返回值
    log.info(
        "Created term with knowledge: term_id=%s knowledge_id=%s user_id=%s",
        term_id,
        knowledge_id,
        user_id,
    )
    return term_id, knowledge_id, name_id  # ← 返回 name_id


def create_term_knowledge(
    term_id: str,
    desc_summary: str,
    desc: str,
    session: Any,
) -> str:
    """Create a TermKnowledge record.

    Returns:
        The generated knowledge_id.
    """
    knowledge_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    session.execute(
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
    log.info("Created term knowledge: %s -> %s", knowledge_id, term_id)
    return knowledge_id

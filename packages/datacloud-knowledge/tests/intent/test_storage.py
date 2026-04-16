from __future__ import annotations

import json
import uuid
from importlib import import_module
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _get_storage_module() -> Any:
    return import_module("datacloud_knowledge.intent.storage")


def _coerce_tags(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    msg = f"Unsupported JSON value type: {type(value)!r}"
    raise TypeError(msg)


def _select_existing_term_id(db_session: Session) -> str:
    row = db_session.execute(text("SELECT term_id FROM whale_datacloud.term LIMIT 1")).fetchone()
    if row is None:
        pytest.skip("No terms in database")
    return str(row[0])


def _select_term_seed_data(db_session: Session) -> tuple[str, str]:
    row = db_session.execute(
        text("SELECT domain_id, term_type_code FROM whale_datacloud.term LIMIT 1")
    ).fetchone()
    if row is None:
        pytest.skip("No terms in database")
    return str(row[0]), str(row[1])


@pytest.mark.intent
@pytest.mark.db_integration
def test_create_user_term_name(db_session: Session) -> None:
    storage_module = _get_storage_module()
    create_user_term_name = storage_module.create_user_term_name

    term_id = _select_existing_term_id(db_session)
    alias_text = f"测试别名_{uuid.uuid4().hex[:8]}"

    name_id = create_user_term_name(
        name_text=alias_text,
        term_id=term_id,
        user_id="test_user_intent",
        session=db_session,
    )

    assert len(name_id) == 36

    verify = db_session.execute(
        text(
            "SELECT term_id, name_text, search_scope "
            "FROM whale_datacloud.term_name "
            "WHERE name_id = :name_id"
        ),
        {"name_id": name_id},
    ).fetchone()
    assert verify is not None

    tags = _coerce_tags(verify[2])
    assert verify[0] == term_id
    assert verify[1] == alias_text
    assert tags["scope_user_id"] == "test_user_intent"
    assert tags["score"] == pytest.approx(1.0)
    assert tags["use_count"] == 1
    assert tags["confirmed_count"] == 1


@pytest.mark.intent
@pytest.mark.db_integration
def test_create_term_with_knowledge(db_session: Session) -> None:
    storage_module = _get_storage_module()
    create_term_with_knowledge = storage_module.create_term_with_knowledge

    domain_id, term_type_code = _select_term_seed_data(db_session)
    suffix = uuid.uuid4().hex[:8]
    term_code = f"intent_term_{suffix}"
    term_name = f"意图测试术语_{suffix}"
    knowledge_text = "用于验证 create_term_with_knowledge 的知识内容。"
    user_id = f"intent_user_{suffix}"

    term_id, knowledge_id = create_term_with_knowledge(
        term_code=term_code,
        term_name=term_name,
        term_type_code=term_type_code,
        domain_id=domain_id,
        knowledge_text=knowledge_text,
        user_id=user_id,
        session=db_session,
    )

    term_row = db_session.execute(
        text(
            "SELECT term_code, term_name, term_type_code, domain_id "
            "FROM whale_datacloud.term WHERE term_id = :term_id"
        ),
        {"term_id": term_id},
    ).fetchone()
    assert term_row is not None
    assert term_row[0] == term_code
    assert term_row[1] == term_name
    assert term_row[2] == term_type_code
    assert term_row[3] == domain_id

    knowledge_row = db_session.execute(
        text(
            'SELECT term_id, desc_summary, "desc" FROM whale_datacloud.term_knowledge '
            "WHERE knowledge_id = :knowledge_id"
        ),
        {"knowledge_id": knowledge_id},
    ).fetchone()
    assert knowledge_row is not None
    assert knowledge_row[0] == term_id
    assert knowledge_row[1] == knowledge_text[:200]
    assert knowledge_row[2] == knowledge_text

    alias_row = db_session.execute(
        text(
            "SELECT name_text, search_scope FROM whale_datacloud.term_name "
            "WHERE term_id = :term_id AND name_text = :name_text"
        ),
        {"term_id": term_id, "name_text": term_name},
    ).fetchone()
    assert alias_row is not None
    assert alias_row[0] == term_name
    assert _coerce_tags(alias_row[1])["scope_user_id"] == user_id


@pytest.mark.intent
@pytest.mark.db_integration
def test_create_term_knowledge(db_session: Session) -> None:
    storage_module = _get_storage_module()
    create_term_knowledge = storage_module.create_term_knowledge

    term_id = _select_existing_term_id(db_session)
    suffix = uuid.uuid4().hex[:8]
    desc_summary = f"测试摘要_{suffix}"
    desc = f"测试知识正文_{suffix}"

    knowledge_id = create_term_knowledge(
        term_id=term_id,
        desc_summary=desc_summary,
        desc=desc,
        session=db_session,
    )

    verify = db_session.execute(
        text(
            'SELECT term_id, desc_summary, "desc" FROM whale_datacloud.term_knowledge '
            "WHERE knowledge_id = :knowledge_id"
        ),
        {"knowledge_id": knowledge_id},
    ).fetchone()
    assert verify is not None
    assert verify[0] == term_id
    assert verify[1] == desc_summary
    assert verify[2] == desc

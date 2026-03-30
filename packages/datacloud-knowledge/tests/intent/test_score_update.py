# ruff: noqa: S101
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


def _get_score_update_module() -> Any:
    return import_module("datacloud_knowledge.intent.score_update")


def _get_types_module() -> Any:
    return import_module("datacloud_knowledge.intent.types")


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


def _create_user_alias(db_session: Session, *, user_id: str) -> str:
    storage_module = _get_storage_module()
    create_user_term_name = storage_module.create_user_term_name

    term_id = _select_existing_term_id(db_session)
    alias_text = f"评分别名_{uuid.uuid4().hex[:8]}"
    return create_user_term_name(
        name_text=alias_text,
        term_id=term_id,
        user_id=user_id,
        session=db_session,
    )


@pytest.mark.intent
@pytest.mark.db_integration
def test_update_score_updates_alias_tags(db_session: Session) -> None:
    score_update_module = _get_score_update_module()
    update_score = score_update_module.update_score

    name_id = _create_user_alias(db_session, user_id="score_user_single")

    update_score(name_id=name_id, success=True, session=db_session)

    row = db_session.execute(
        text("SELECT search_scope FROM whale_datacloud.term_name WHERE name_id = :name_id"),
        {"name_id": name_id},
    ).fetchone()
    assert row is not None

    tags = _coerce_tags(row[0])
    assert tags["scope_user_id"] == "score_user_single"
    assert tags["use_count"] == 2
    assert tags["confirmed_count"] == 2
    assert tags["score"] == pytest.approx(2 / 3)
    assert tags["last_used_at"]


@pytest.mark.intent
@pytest.mark.db_integration
def test_batch_update_scores_updates_multiple_aliases(db_session: Session) -> None:
    score_update_module = _get_score_update_module()
    types_module = _get_types_module()
    batch_update_scores = score_update_module.batch_update_scores
    score_update_record = types_module.ScoreUpdateRecord

    first_name_id = _create_user_alias(db_session, user_id="score_user_batch_1")
    second_name_id = _create_user_alias(db_session, user_id="score_user_batch_2")

    batch_update_scores(
        records=(
            score_update_record(name_id=first_name_id, success=True),
            score_update_record(name_id=second_name_id, success=False),
        ),
        session=db_session,
    )

    rows = db_session.execute(
        text(
            "SELECT name_id, search_scope FROM whale_datacloud.term_name "
            "WHERE name_id IN (:first_name_id, :second_name_id)"
        ),
        {"first_name_id": first_name_id, "second_name_id": second_name_id},
    ).fetchall()
    assert len(rows) == 2

    rows_by_id = {str(row[0]): _coerce_tags(row[1]) for row in rows}
    assert rows_by_id[first_name_id]["use_count"] == 2
    assert rows_by_id[first_name_id]["confirmed_count"] == 2
    assert rows_by_id[first_name_id]["score"] == pytest.approx(2 / 3)
    assert rows_by_id[second_name_id]["use_count"] == 2
    assert rows_by_id[second_name_id]["confirmed_count"] == 1
    assert rows_by_id[second_name_id]["score"] == pytest.approx(1 / 3)


@pytest.mark.intent
def test_recalculate_score_uses_decay_adjusted_ratio() -> None:
    score_update_module = _get_score_update_module()
    recalculate_score = score_update_module._recalculate_score

    assert recalculate_score(confirmed_count=3, use_count=5, decay=0.8) == pytest.approx(0.4)

"""Unit tests for session.metadata."""

from __future__ import annotations

from datacloud_analysis.session.metadata import SessionMetadata, build_run_config


def test_auto_generates_thread_id() -> None:
    meta = SessionMetadata(message_id="m1", session_id="s1", user_id="u1")
    assert meta.thread_id.startswith("thread-")


def test_explicit_thread_id_preserved() -> None:
    meta = SessionMetadata(message_id="m1", session_id="s1", user_id="u1", thread_id="my-thread")
    assert meta.thread_id == "my-thread"


def test_checkpoint_metadata_contains_business_ids() -> None:
    meta = SessionMetadata(
        message_id="msg-001",
        session_id="sess-001",
        user_id="user-42",
        attachment_ids=["att-1", "att-2"],
    )
    md = meta.to_checkpoint_metadata()
    assert md["message_id"] == "msg-001"
    assert md["session_id"] == "sess-001"
    assert md["user_id"] == "user-42"
    assert md["attachment_ids"] == ["att-1", "att-2"]


def test_build_run_config_structure() -> None:
    meta = SessionMetadata(message_id="m", session_id="s", user_id="u")
    config = build_run_config(meta)
    assert "configurable" in config
    assert config["configurable"]["thread_id"] == meta.thread_id

"""test_llm_checkpoint.py — TDD 红阶段：llm_checkpoint 模块尚未实现，全部用例应失败。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

# ─── 常量内容检验 ──────────────────────────────────────────────────────────────


def test_checkpoint_reply_guides_user_to_resend() -> None:
    """CHECKPOINT_REPLY 应告知用户'重新发送同样的问题'。"""
    from datacloud_analysis.orchestration.execution.llm_checkpoint import CHECKPOINT_REPLY

    assert "重新发送同样的问题" in CHECKPOINT_REPLY


def test_checkpoint_reply_mentions_service_unavailable() -> None:
    from datacloud_analysis.orchestration.execution.llm_checkpoint import CHECKPOINT_REPLY

    assert "不可用" in CHECKPOINT_REPLY or "繁忙" in CHECKPOINT_REPLY


def test_expired_reply_is_non_empty() -> None:
    from datacloud_analysis.orchestration.execution.llm_checkpoint import EXPIRED_REPLY

    assert len(EXPIRED_REPLY.strip()) > 10


# ─── save_llm_failure_checkpoint ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_uses_correct_redis_key() -> None:
    """key 格式必须是 llm:checkpoint:{session_id}。"""
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        save_llm_failure_checkpoint,
    )

    redis = AsyncMock()
    redis.setex = AsyncMock(return_value=True)

    await save_llm_failure_checkpoint(
        redis_client=redis,
        session_id="sess-123",
        state={"user_query": "查询小米营收"},
        completed_steps=2,
        exc=Exception("model down"),
    )

    redis.setex.assert_called_once()
    key_used = redis.setex.call_args[0][0]
    assert key_used == "llm:checkpoint:sess-123"


@pytest.mark.asyncio
async def test_save_sets_ttl_3600() -> None:
    """TTL 必须是 3600 秒。"""
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        save_llm_failure_checkpoint,
    )

    redis = AsyncMock()
    redis.setex = AsyncMock(return_value=True)

    await save_llm_failure_checkpoint(
        redis_client=redis,
        session_id="sess-ttl",
        state={},
        completed_steps=0,
        exc=Exception("error"),
    )

    ttl = redis.setex.call_args[0][1]
    assert ttl == 3600


@pytest.mark.asyncio
async def test_save_payload_contains_required_fields() -> None:
    """持久化的 JSON 必须包含 session_id / completed_steps / error_type / saved_at。"""
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        save_llm_failure_checkpoint,
    )

    redis = AsyncMock()
    redis.setex = AsyncMock(return_value=True)

    await save_llm_failure_checkpoint(
        redis_client=redis,
        session_id="sess-payload",
        state={"user_query": "test"},
        completed_steps=3,
        exc=ValueError("something failed"),
    )

    raw_payload = redis.setex.call_args[0][2]
    payload = json.loads(raw_payload)
    assert payload["session_id"] == "sess-payload"
    assert payload["completed_steps"] == 3
    assert payload["error_type"] == "ValueError"
    assert "saved_at" in payload


@pytest.mark.asyncio
async def test_save_returns_true_on_success() -> None:
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        save_llm_failure_checkpoint,
    )

    redis = AsyncMock()
    redis.setex = AsyncMock(return_value=True)

    result = await save_llm_failure_checkpoint(
        redis_client=redis,
        session_id="sess-ok",
        state={},
        completed_steps=1,
        exc=Exception("err"),
    )
    assert result is True


@pytest.mark.asyncio
async def test_save_no_redis_returns_false_without_crash() -> None:
    """redis_client=None 时优雅降级，返回 False，不抛异常。"""
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        save_llm_failure_checkpoint,
    )

    result = await save_llm_failure_checkpoint(
        redis_client=None,
        session_id="sess-no-redis",
        state={},
        completed_steps=0,
        exc=Exception("error"),
    )
    assert result is False


@pytest.mark.asyncio
async def test_save_redis_connection_error_returns_false() -> None:
    """Redis 操作本身抛异常时返回 False，不向上传播。"""
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        save_llm_failure_checkpoint,
    )

    redis = AsyncMock()
    redis.setex = AsyncMock(side_effect=ConnectionError("redis unreachable"))

    result = await save_llm_failure_checkpoint(
        redis_client=redis,
        session_id="sess-redis-err",
        state={},
        completed_steps=0,
        exc=Exception("model error"),
    )
    assert result is False


# ─── load_llm_failure_checkpoint ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_returns_checkpoint_when_exists() -> None:
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        load_llm_failure_checkpoint,
    )

    stored = {
        "session_id": "sess-load",
        "completed_steps": 2,
        "state_snapshot": {"user_query": "hi"},
    }
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps(stored).encode())

    result = await load_llm_failure_checkpoint(redis, "sess-load")

    assert result is not None
    assert result["session_id"] == "sess-load"
    assert result["completed_steps"] == 2
    redis.get.assert_called_once_with("llm:checkpoint:sess-load")


@pytest.mark.asyncio
async def test_load_returns_none_when_key_missing() -> None:
    """Redis 返回 None（key 不存在或已过期）时返回 None。"""
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        load_llm_failure_checkpoint,
    )

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)

    result = await load_llm_failure_checkpoint(redis, "sess-missing")
    assert result is None


@pytest.mark.asyncio
async def test_load_returns_none_for_non_object_payload() -> None:
    """If stored payload is valid JSON but not an object, loader should return None."""
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        load_llm_failure_checkpoint,
    )

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps(["bad", "payload"]).encode())

    result = await load_llm_failure_checkpoint(redis, "sess-bad")
    assert result is None


@pytest.mark.asyncio
async def test_load_no_redis_returns_none() -> None:
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        load_llm_failure_checkpoint,
    )

    result = await load_llm_failure_checkpoint(None, "sess-no-redis")
    assert result is None


@pytest.mark.asyncio
async def test_load_redis_error_returns_none() -> None:
    """Redis 操作失败时返回 None，不抛异常。"""
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        load_llm_failure_checkpoint,
    )

    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=ConnectionError("redis down"))

    result = await load_llm_failure_checkpoint(redis, "sess-err")
    assert result is None


# ─── delete_llm_failure_checkpoint ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_calls_redis_delete_with_correct_key() -> None:
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        delete_llm_failure_checkpoint,
    )

    redis = AsyncMock()
    redis.delete = AsyncMock(return_value=1)

    await delete_llm_failure_checkpoint(redis, "sess-del")
    redis.delete.assert_called_once_with("llm:checkpoint:sess-del")


@pytest.mark.asyncio
async def test_delete_no_redis_no_crash() -> None:
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        delete_llm_failure_checkpoint,
    )

    await delete_llm_failure_checkpoint(None, "sess-no-redis")  # 不抛异常即通过


@pytest.mark.asyncio
async def test_delete_redis_error_no_crash() -> None:
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        delete_llm_failure_checkpoint,
    )

    redis = AsyncMock()
    redis.delete = AsyncMock(side_effect=ConnectionError("redis down"))

    await delete_llm_failure_checkpoint(redis, "sess-err")  # 不抛异常即通过

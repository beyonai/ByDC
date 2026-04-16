"""llm_checkpoint.py — LLM 全部不可用时的 Checkpoint 保存/加载，以及用户引导回复。

当主模型和备用模型全部不可用时：
1. 调用 save_llm_failure_checkpoint 将当前处理进度写入 Redis
2. 向用户返回 CHECKPOINT_REPLY，引导其稍后重发同一问题
3. 用户重发后，后端检测到 checkpoint，从中断处继续处理

Redis Key 格式：llm:checkpoint:{session_id}
TTL：3600 秒（1 小时），超时后 checkpoint 自动失效
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_CHECKPOINT_TTL: int = 3600  # 秒

# ─── 用户可见引导文案 ───────────────────────────────────────────────────────────

CHECKPOINT_REPLY: str = (
    "⚠️ 当前 AI 服务暂时不可用（服务器繁忙或网络异常），您的问题已被记录。\n\n"
    "请稍等片刻后，**重新发送同样的问题**，系统将自动从中断处继续处理，无需重新开始。"
)

EXPIRED_REPLY: str = "您之前的问题处理记录已过期，将重新为您查询，请稍候。"


# ─── 内部工具函数 ───────────────────────────────────────────────────────────────


def _checkpoint_key(session_id: str) -> str:
    """生成 Redis key。"""
    return f"llm:checkpoint:{session_id}"


# ─── 公开 API ───────────────────────────────────────────────────────────────────


async def save_llm_failure_checkpoint(
    redis_client: Any,
    session_id: str,
    state: dict[str, Any],
    completed_steps: int,
    exc: Exception,
) -> bool:
    """将 LLM 失败断点保存到 Redis。

    Args:
        redis_client: 异步 Redis 客户端（aioredis / redis.asyncio）。为 None 时优雅降级。
        session_id:   会话 ID，用作 Redis key 的一部分。
        state:        当前 GraphState 快照，用于恢复时重建上下文。
        completed_steps: 已完成的 react 轮次数（用于跳过已执行步骤）。
        exc:          触发断点的异常，记录错误类型和摘要。

    Returns:
        True 表示成功保存，False 表示无 Redis 或保存失败（不抛异常）。
    """
    if redis_client is None:
        logger.warning("[LLM] 无 Redis 客户端，跳过 checkpoint 保存 session=%s", session_id)
        return False

    try:
        checkpoint: dict[str, Any] = {
            "session_id": session_id,
            "saved_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "state_snapshot": state,
            "completed_steps": completed_steps,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:200],
        }
        key = _checkpoint_key(session_id)
        payload = json.dumps(checkpoint, ensure_ascii=False, default=str)
        await redis_client.setex(key, _CHECKPOINT_TTL, payload)
        logger.warning("[LLM] 已保存断点 key=%s completed_steps=%d", key, completed_steps)
        return True
    except Exception as save_exc:
        logger.error("[LLM] checkpoint 保存失败: %s", save_exc)
        return False


async def load_llm_failure_checkpoint(
    redis_client: Any,
    session_id: str,
) -> dict[str, Any] | None:
    """从 Redis 加载 LLM 失败断点。

    Returns:
        断点字典，若不存在、已过期或加载失败则返回 None。
    """
    if redis_client is None:
        return None

    try:
        key = _checkpoint_key(session_id)
        data = await redis_client.get(key)
        if not data:
            return None
        payload: Any = json.loads(data)
        if not isinstance(payload, dict):
            logger.warning(
                "[LLM] checkpoint payload is not a dict, key=%s type=%s",
                key,
                type(payload).__name__,
            )
            return None
        return payload
    except Exception as exc:
        logger.error("[LLM] checkpoint 加载失败: %s", exc)
        return None


async def delete_llm_failure_checkpoint(
    redis_client: Any,
    session_id: str,
) -> None:
    """删除 Redis 中的 LLM 失败断点（恢复成功后清理，避免影响下次正常问答）。"""
    if redis_client is None:
        return

    try:
        key = _checkpoint_key(session_id)
        await redis_client.delete(key)
        logger.info("[LLM] 已删除断点 key=%s", key)
    except Exception as exc:
        logger.error("[LLM] checkpoint 删除失败: %s", exc)

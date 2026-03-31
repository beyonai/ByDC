"""
Gateway Progress Reporter

在 SDK 查询管线执行期间，通过 AgentContext 向前端推送实时进度事件。
使用鸭子类型，避免 datacloud-data 依赖 gateway_sdk。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# EventType.REASONING_LOG_DELTA.value
_EVENT_REASONING_LOG_DELTA = "reasoningLogDelta"
# SseReasonMessageType.think_title.value
_CONTENT_THINK_TITLE = "3003"
# SseReasonMessageType.think_text.value
_CONTENT_THINK_TEXT = "1002"


class GatewayProgressReporter:
    """
    封装 AgentContext.emit_chunk()，在 SDK 查询管线的各阶段向前端推送进度事件。

    所有方法均 async，异常静默处理（不中断主流程）。

    Args:
        gateway_context: gateway_sdk.AgentContext 实例，声明为 Any 避免循环依赖。
    """

    def __init__(self, gateway_context: Any) -> None:
        self._ctx = gateway_context

    async def on_plan_generating(self, question: str) -> None:
        """推送：开始生成查询计划。"""
        await self._emit("正在生成查询计划", f"问题：{question}")

    async def on_plan_generating_token(self, token: str) -> None:
        """推送：计划生成流式 token。仅推送 text，不推送 title 避免刷屏。"""
        await self._emit_text(token)

    async def on_plan_generated(self, summary: str) -> None:
        """推送：计划生成完成摘要。"""
        await self._emit("查询计划已生成", summary)

    async def on_plan_validation_retry(self, retry_count: int, errors: list[str]) -> None:
        """推送：计划校验失败，正在重试。"""
        errors_text = "；".join(errors[:3])
        await self._emit(
            f"计划校验失败，正在重试（第 {retry_count} 次）",
            f"错误：{errors_text}",
        )

    async def on_step_executing(self, step_id: str, step_type: str, desc: str = "") -> None:
        """推送：开始执行某个查询步骤。"""
        detail = f"▶ 步骤 {step_id}（{step_type}）"
        if desc:
            detail += f"：{desc}"
        await self._emit("执行查询步骤", detail)

    async def on_step_completed(self, step_id: str, row_count: int | None = None) -> None:
        """推送：某个查询步骤执行完成。"""
        detail = f"✓ 步骤 {step_id} 完成"
        if row_count is not None:
            detail += f"，返回 {row_count} 条记录"
        await self._emit("查询步骤完成", detail)

    async def on_aggregating(self, strategy: str) -> None:
        """推送：开始聚合结果。"""
        await self._emit("正在聚合结果", f"策略：{strategy}")

    async def on_aggregation_completed(self, record_count: int) -> None:
        """推送：聚合完成。"""
        await self._emit("结果聚合完成", f"共 {record_count} 条记录")

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    async def _emit(self, title: str, text: str) -> None:
        """推送 think_title + think_text 两条事件。"""
        try:
            # chunk = _make_chunk(title)
            # await self._ctx.emit_chunk(
            #     chunk,
            #     event_type=_EVENT_REASONING_LOG_DELTA,
            #     content_type=_CONTENT_THINK_TITLE,
            # )

            text = f"【{title}】\n{text} \n\n"
            chunk = _make_chunk(text)
            await self._ctx.emit_chunk(
                chunk,
                event_type=_EVENT_REASONING_LOG_DELTA,
                content_type=_CONTENT_THINK_TEXT,
            )
        except Exception:
            logger.debug("GatewayProgressReporter._emit failed", exc_info=True)

    async def _emit_text(self, text: str) -> None:
        """仅推送 think_text（用于流式 token，不重复推送 title）。"""
        try:
            chunk = _make_chunk(text)
            await self._ctx.emit_chunk(
                chunk,
                event_type=_EVENT_REASONING_LOG_DELTA,
                content_type=_CONTENT_THINK_TEXT,
            )
        except Exception as e:
            logger.debug("GatewayProgressReporter._emit_text failed", exc_info=True)


def _make_chunk(content: str) -> Any:
    """构造 StreamChunkEvent，若 gateway_sdk 不可用则返回简单对象。"""
    try:
        from by_framework.core.protocol.events import StreamChunkEvent  # noqa: PLC0415
        return StreamChunkEvent(content=content)
    except ImportError:
        # 兜底：返回带 content 属性的简单对象
        class _Chunk:
            pass
        c = _Chunk()
        c.content = content  # type: ignore[attr-defined]
        return c

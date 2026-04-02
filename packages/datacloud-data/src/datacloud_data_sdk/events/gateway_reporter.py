"""
Gateway Progress Reporter

在 SDK 查询管线执行期间，通过 reasoning think_text 事件向前端推送实时进度。
使用鸭子类型，避免 datacloud-data 依赖 gateway_sdk。

层级规则：
  - 里程碑方法（on_plan_generating / on_step_executing 等）：
      第一层 = emit_state(标题)，第二层 = emit_chunk(文本内容)
  - 流式 token（on_plan_generating_token）：
      不新开层级，复用 on_plan_generating 创建的 message_id 持续追加
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_data_sdk.stream_text import coerce_stream_chunk_text

logger = logging.getLogger(__name__)

_THINK_EVENT_TYPE = "reasoningLogDelta"
_THINK_CONTENT_TYPE = "1002"


class GatewayProgressReporter:
    """
    封装 AgentContext.emit_state() + emit_chunk()，在 SDK 查询管线的各阶段向前端推送思考事件。

    若网关上下文不支持 reasoning 事件，则降级为 sub_step() + emit_chunk()。

    所有方法均 async，异常静默处理（不中断主流程）。

    Args:
        gateway_context: gateway_sdk.AgentContext 实例，声明为 Any 避免循环依赖。
    """

    def __init__(self, gateway_context: Any) -> None:
        self._ctx = gateway_context
        # 流式 token 需要挂载到 on_plan_generating 创建的思考节点下
        self._plan_gen_m_id: str = ""
        self._plan_gen_p_m_id: str = ""

    async def on_plan_generating(self, question: str) -> None:
        """推送：开始生成查询计划（第一层），并记录消息 id 供后续流式 token 追加。"""
        try:
            m_id, p_m_id = await self._emit_reasoning_block(
                "正在生成查询计划",
                f"问题：{question}",
            )
            self._plan_gen_m_id = m_id
            self._plan_gen_p_m_id = p_m_id
        except Exception:
            logger.debug("on_plan_generating failed", exc_info=True)

    async def on_plan_generating_token(self, token: str) -> None:
        """推送：计划生成流式 token，追加到 on_plan_generating 的思考节点下，不新开层级。"""
        try:
            await self._emit_chunk(
                token,
                message_id=self._plan_gen_m_id,
                parent_message_id=self._plan_gen_p_m_id,
            )
        except Exception:
            logger.debug("on_plan_generating_token failed", exc_info=True)

    async def on_plan_generated(self, summary: str) -> None:
        """推送：计划生成完成摘要，并清除流式 token 的挂载 id。"""
        self._plan_gen_m_id = ""
        self._plan_gen_p_m_id = ""
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
        """第一层 emit_state(title)，第二层 emit_chunk(text)。"""
        try:
            await self._emit_reasoning_block(title, text)
        except Exception:
            logger.debug("GatewayProgressReporter._emit failed", exc_info=True)

    def _reasoning_kwargs(
        self,
        *,
        message_id: str = "",
        parent_message_id: str = "",
    ) -> dict[str, str]:
        kwargs = {
            "event_type": _THINK_EVENT_TYPE,
            "content_type": _THINK_CONTENT_TYPE,
        }
        if message_id:
            kwargs["message_id"] = message_id
        if parent_message_id:
            kwargs["parent_message_id"] = parent_message_id
        return kwargs

    def _new_message_id(self) -> str:
        generator = getattr(self._ctx, "generate_message_id", None)
        if callable(generator):
            try:
                generated = str(generator())
                if generated:
                    return generated
            except Exception:
                logger.debug("generate_message_id failed", exc_info=True)
        return ""

    def _root_message_id(self) -> str:
        return str(getattr(self._ctx, "message_id", "") or "")

    async def _emit_reasoning_block(self, title: str, text: str) -> tuple[str, str]:
        message_id = self._new_message_id()
        parent_message_id = self._root_message_id()

        try:
            await self._emit_state(
                title,
                message_id=message_id,
                parent_message_id=parent_message_id,
            )
            await self._emit_chunk(
                text,
                message_id=message_id,
                parent_message_id=parent_message_id,
            )
            return message_id, parent_message_id
        except Exception as exc:
            logger.debug(
                "emit reasoning block directly failed, fallback to sub_step",
                exc_info=True,
            )

        sub_step = getattr(self._ctx, "sub_step", None)
        if sub_step is None:
            raise RuntimeError(
                "gateway_context does not support reasoning emit or sub_step"
            ) from exc

        async with sub_step(title) as (fallback_m_id, fallback_p_m_id):
            await self._ctx.emit_chunk(coerce_stream_chunk_text(text))
        return str(fallback_m_id), str(fallback_p_m_id)

    async def _emit_state(
        self,
        content: str,
        *,
        message_id: str = "",
        parent_message_id: str = "",
    ) -> None:
        emit_state = getattr(self._ctx, "emit_state", None)
        if emit_state is None:
            raise AttributeError("gateway_context has no emit_state")
        await emit_state(
            content,
            **self._reasoning_kwargs(
                message_id=message_id,
                parent_message_id=parent_message_id,
            ),
        )

    async def _emit_chunk(
        self,
        content: str,
        *,
        message_id: str = "",
        parent_message_id: str = "",
    ) -> None:
        await self._ctx.emit_chunk(
            coerce_stream_chunk_text(content),
            **self._reasoning_kwargs(
                message_id=message_id,
                parent_message_id=parent_message_id,
            ),
        )

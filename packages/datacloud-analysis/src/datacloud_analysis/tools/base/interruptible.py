"""可中断恢复工具基类。

所有需要等待外部响应的工具都应继承 InterruptibleTool，只需实现两个方法：
- _build_interrupt_payload(**kwargs) -> BeforeInterruptResult
- _handle_resume(resume: ResumeData, **kwargs) -> Any

基类负责中断/恢复的完整生命周期，包括副作用调用：
  1. _build_interrupt_payload() — 构造 payload + side_effect_kwargs（每次执行都会调，需幂等）
  2. _dispatch_side_effect()    — 仅首次执行时调用（resume 重跑时自动跳过）
  3. interrupt()                — 图挂起，checkpoint 写 PG
  4. _handle_resume()           — resume 后处理结果

幂等保障：LangGraph resume 时节点从头重跑，_dispatch_side_effect 会被调用两次。
基类通过读取 LangGraph 内部 scratchpad.resume 列表来判断当前是否为 resume 重跑：
- 首次执行：scratchpad.resume 为空 → 执行副作用
- resume 重跑：scratchpad.resume 已有值 → 跳过副作用，直接走到 interrupt() 取 resume value
这是纯内存的进程内判断，无需 store、无需 state 变更，多节点场景下每个节点都有自己的
scratchpad，天然正确。
"""

from __future__ import annotations

import abc
import logging
from typing import Any, Literal

from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import BaseTool
from langgraph.types import interrupt

logger = logging.getLogger(__name__)

InterruptReasonCode = Literal[
    "ASK_USER",
    "CONFIRM_ACTION",
    "ASYNC_TOOL_WAIT",
    "AGENT_DELEGATE_WAIT",
    "APPROVAL_GATE",
]


class ResumeData:
    """interrupt() 返回值的标准化包装。

    worker 发来的 reply_data 结构因场景而异：
    - ASK_USER:            字符串，或 {"status": "ok", "data": "用户回答"}
    - AGENT_DELEGATE_WAIT: {"status": "done", "conclusion": "子Agent结论文本"}
    基类统一解析，子类通过 .data 取最终有效载荷。
    """

    __slots__ = ("status", "data", "error")

    _OK_STATUSES = frozenset({"ok", "done", "completed", "success"})

    def __init__(self, raw: Any) -> None:
        if isinstance(raw, dict):
            self.status: str = str(raw.get("status") or "ok")
            # 优先取 "data"，其次取 "conclusion"（子 Agent 返回场景）
            # 使用 "data" in raw 而非 or，避免空字符串、0、[] 等 falsy 值被错误丢弃
            if "data" in raw:
                self.data: Any = raw["data"]
            else:
                self.data = raw.get("conclusion")
            self.error: str | None = raw.get("error")
        else:
            self.status = "ok"
            self.data = raw
            self.error = None

    @property
    def ok(self) -> bool:
        return self.status in self._OK_STATUSES

    @property
    def cancelled(self) -> bool:
        return self.status == "cancel"

    @property
    def timed_out(self) -> bool:
        return self.status == "timeout"

    def __repr__(self) -> str:
        return f"ResumeData(status={self.status!r}, data={self.data!r}, error={self.error!r})"


class BeforeInterruptResult:
    """_build_interrupt_payload() 的返回值。

    Attributes:
        reason_code:       中断类型，worker 和基类按此分发
        display:           发给前端展示的数据
        resume_schema:     声明 resume data 的 JSON Schema
        correlation_id:    关联外部任务 ID（如子 Agent message_id）
        timeout_seconds:   超时秒数
        side_effect_kwargs: 副作用调用参数，由基类 _dispatch_side_effect 使用，
                            不会写入 interrupt payload（避免污染）
    """

    __slots__ = (
        "reason_code",
        "display",
        "resume_schema",
        "correlation_id",
        "timeout_seconds",
        "side_effect_kwargs",
    )

    def __init__(
        self,
        reason_code: InterruptReasonCode,
        display: dict[str, Any],
        resume_schema: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        timeout_seconds: int | None = None,
        side_effect_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.display = display
        self.resume_schema = resume_schema or {"type": "object"}
        self.correlation_id = correlation_id
        self.timeout_seconds = timeout_seconds
        # side_effect_kwargs 只给基类用，不写入 interrupt payload
        self.side_effect_kwargs: dict[str, Any] = side_effect_kwargs or {}

    def to_interrupt_payload(self) -> dict[str, Any]:
        """构造传给 interrupt() 的 payload，不含 side_effect_kwargs。"""
        payload: dict[str, Any] = {
            "reason_code": self.reason_code,
            "display": self.display,
            "resume_schema": self.resume_schema,
        }
        if self.correlation_id is not None:
            payload["correlation_id"] = self.correlation_id
        if self.timeout_seconds is not None:
            payload["timeout_seconds"] = self.timeout_seconds
        return payload


class InterruptibleTool(BaseTool, abc.ABC):
    """支持中断恢复的工具基类。

    子类只需实现两个方法：

    1. _build_interrupt_payload(**kwargs) -> BeforeInterruptResult
       每次执行（含 resume 重跑）都会调用。
       - 通过 side_effect_kwargs 传递副作用参数（如 call_agent 的入参）
       - 副作用参数中的 ID（message_id 等）必须稳定（基于内容 hash），保证幂等

    2. _handle_resume(resume: ResumeData, **kwargs) -> Any
       拿到 resume 数据后，返回工具最终输出给 LLM。

    基类 _dispatch_side_effect 按 reason_code 内置分发逻辑：
    - AGENT_DELEGATE_WAIT: 调用 context.call_agent(**side_effect_kwargs)
    子类可覆盖此方法实现自定义副作用。
    """

    handle_tool_error: bool = True

    @abc.abstractmethod
    async def _build_interrupt_payload(self, **kwargs: Any) -> BeforeInterruptResult:
        """构造 interrupt payload 及副作用参数。

        每次执行都会调用（含 resume 重跑），副作用参数中的 ID 必须稳定。
        """

    @abc.abstractmethod
    async def _handle_resume(self, resume: ResumeData, **kwargs: Any) -> Any:
        """将 resume 数据转换为工具最终返回值。"""

    async def _dispatch_side_effect(
        self,
        context: Any,
        before: BeforeInterruptResult,
        **kwargs: Any,  # noqa: ARG002
    ) -> None:
        """按 reason_code 分发副作用。resume 重跑时也会调用，依赖幂等保障。

        内置行为：
        - AGENT_DELEGATE_WAIT: 调用 context.call_agent(**side_effect_kwargs)

        子类可覆盖以实现自定义副作用（如提交异步任务、请求审批等）。
        """
        if not before.side_effect_kwargs:
            return

        if before.reason_code == "AGENT_DELEGATE_WAIT":
            if context is None:
                logger.error("AGENT_DELEGATE_WAIT: _context is None, cannot call_agent")
                return
            call_agent = getattr(context, "call_agent", None)
            if not callable(call_agent):
                logger.error("AGENT_DELEGATE_WAIT: context has no call_agent method")
                return
            logger.info(
                "InterruptibleTool[%s] dispatching call_agent: target=%s",
                self.name,
                before.side_effect_kwargs.get("target_agent_type"),
            )
            await call_agent(**before.side_effect_kwargs)

    async def _arun(self, **kwargs: Any) -> Any:
        # 优先从 kwargs 取 _context（测试/直接调用场景）
        # LLM 调用工具时不传 _context，需从 LangGraph config 的 configurable 中读取
        context = kwargs.get("_context")
        runnable_config: dict[str, Any] = {}
        if context is None:
            try:
                runnable_config = var_child_runnable_config.get()
                context = (runnable_config.get("configurable") or {}).get("gateway_context")
            except LookupError:
                pass
        if context is not None:
            kwargs["_context"] = context

        # 1. 子类构造 payload + side_effect_kwargs
        before: BeforeInterruptResult = await self._build_interrupt_payload(**kwargs)

        # 2. 幂等保护：通过 LangGraph scratchpad.resume 判断是否为 resume 重跑
        #    首次执行：scratchpad.resume 为空 → 执行副作用
        #    resume 重跑：scratchpad.resume 已有值（interrupt() 将直接返回）→ 跳过副作用
        #    scratchpad 是节点级别的，多节点部署下每个节点独立，天然正确，无需 store/state
        is_resume_rerun = self._is_resume_rerun()
        if not is_resume_rerun:
            await self._dispatch_side_effect(context, before, **kwargs)
        else:
            logger.debug(
                "InterruptibleTool[%s] resume rerun detected, skipping _dispatch_side_effect",
                self.name,
            )

        # 3. 挂起，等待 ResumeCommand
        #    首次执行：抛出 GraphInterrupt，图挂起
        #    resume 重跑：scratchpad 中有 resume value，直接返回，不再挂起
        raw_resume = interrupt(before.to_interrupt_payload())

        # 4. 标准化 resume 数据
        resume = ResumeData(raw_resume)
        logger.debug(
            "InterruptibleTool[%s] resumed: reason_code=%s resume=%r",
            self.name,
            before.reason_code,
            resume,
        )

        # 5. 子类处理结果
        return await self._handle_resume(resume, **kwargs)

    def _is_resume_rerun(self) -> bool:
        """判断当前执行是否为 LangGraph resume 重跑。

        LangGraph 有两条 resume 路径，需要同时检查：

        1. scratchpad.resume 非空：
           同一节点内第二个及以后的 interrupt() 调用，resume 值已经通过
           scratchpad.resume.append() 记录（见 interrupt() 源码）。

        2. scratchpad.get_null_resume(False) 非 None：
           Command(resume=...) 写入的是 (NULL_TASK_ID, RESUME, value)，
           在 _scratchpad() 初始化时存入 null_resume_write，不体现在
           scratchpad.resume 列表里（列表初始为空）。
           get_null_resume(consume=False) 不消费，只探测是否存在。

        若不在 LangGraph 图执行上下文中（如单元测试），返回 False（始终执行副作用）。
        """
        try:
            from langgraph._internal._constants import CONFIG_KEY_SCRATCHPAD  # noqa: PLC0415
            from langgraph.config import get_config  # noqa: PLC0415

            scratchpad = get_config()["configurable"][CONFIG_KEY_SCRATCHPAD]
            return bool(scratchpad.resume) or scratchpad.get_null_resume(False) is not None
        except Exception:
            return False

    def _run(self, **kwargs: Any) -> Any:
        raise NotImplementedError("InterruptibleTool requires async invocation via _arun")

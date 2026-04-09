"""子 Agent 委托工具。

将任务委托给另一个 Agent 执行，并同步等待其返回结果。

中断流程（由 InterruptibleTool 基类统一管理）：
1. _build_interrupt_payload() 构造委托参数，message_id 基于内容 hash 保证幂等
2. 基类 _dispatch_side_effect() 调用 context.call_agent(...)
   resume 重跑时再次调用，框架侧因 message_id 相同自动去重
3. interrupt() 挂起图，等待子 Agent 发 ResumeCommand
4. _handle_resume() 将子 Agent 结论透传给 LLM
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from datacloud_analysis.tools.base import BeforeInterruptResult, InterruptibleTool, ResumeData

logger = logging.getLogger(__name__)


class DelegateToAgentTool(InterruptibleTool):
    """委托子 Agent 执行任务，同步等待结果后继续。"""

    model_config = {"arbitrary_types_allowed": True}

    target_agent_type: str
    agent_name: str

    # ToolCallLoggingMiddleware 识别标记
    _is_agent_delegate: bool = True

    # ---------- InterruptibleTool 协议 ----------

    async def _build_interrupt_payload(  # type: ignore[override]
        self,
        content: str | None = None,
        _context: Any = None,
        delegate_policy: dict[str, Any] | None = None,  # noqa: ARG002
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> BeforeInterruptResult:
        resolved_content = self._resolve_content(content, kwargs)
        delegate_metadata = self._build_delegate_metadata(_context, metadata)

        # message_id 基于 (target, content, session) 的 hash，保证 resume 重跑时幂等
        stable_message_id = self._stable_message_id(
            target=self.target_agent_type,
            content=resolved_content,
            context=_context,
        )

        call_agent_kwargs = self._build_call_agent_kwargs(
            resolved_content=resolved_content,
            message_id=stable_message_id,
            context=_context,
            delegate_payload=dict(payload) if isinstance(payload, dict) else {},
            delegate_metadata=delegate_metadata,
        )

        return BeforeInterruptResult(
            reason_code="AGENT_DELEGATE_WAIT",
            display={
                "target_agent_type": self.target_agent_type,
                "target_agent_name": self.agent_name,
                "delegate_content": resolved_content,
            },
            correlation_id=stable_message_id,
            # 基类 _dispatch_side_effect 用此调用 context.call_agent
            side_effect_kwargs=call_agent_kwargs,
        )

    async def _handle_resume(  # type: ignore[override]
        self,
        resume: ResumeData,
        **_kwargs: Any,
    ) -> Any:
        if not resume.ok:
            logger.warning(
                "DelegateToAgentTool[%s] resume non-ok: status=%s error=%s",
                self.target_agent_type,
                resume.status,
                resume.error,
            )
            return f"[子Agent {self.agent_name} 执行失败: {resume.error or resume.status}]"

        if resume.data is None:
            logger.warning(
                "DelegateToAgentTool[%s] resume.data is None, raw status=%s",
                self.target_agent_type,
                resume.status,
            )
            return f"[子Agent {self.agent_name} 已完成，但未返回结论内容]"

        return resume.data

    # ---------- 辅助方法 ----------

    def _resolve_content(self, content: str | None, kwargs: dict[str, Any]) -> str:
        resolved = str(
            content
            or kwargs.get("content")
            or kwargs.get("question")
            or kwargs.get("query")
            or kwargs.get("description")
            or kwargs.get("kwargs", {}).get("content")
            or ""
        ).strip()
        return resolved or f"Please handle request related to {self.agent_name}."

    def _stable_message_id(self, *, target: str, content: str, context: Any) -> str:
        """基于 (target, content, session_id) 生成稳定 message_id。

        LangGraph resume 时节点重跑，此方法会再次调用，
        相同输入必须返回相同 ID，框架侧凭此去重，避免子 Agent 被重复调起。
        """
        session_id = str(getattr(context, "session_id", "") or "")
        raw = f"{target}:{content}:{session_id}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def _build_delegate_metadata(
        self,
        context: Any,
        extra_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        meta: dict[str, Any] = dict(extra_metadata) if isinstance(extra_metadata, dict) else {}

        parent_session_id = str(getattr(context, "session_id", "") or "").strip()
        current_command = getattr(context, "current_command", None)
        current_extra_payload = (
            getattr(current_command, "extra_payload", {}) if current_command is not None else {}
        )
        current_header = getattr(current_command, "header", None)
        current_header_metadata = (
            getattr(current_header, "metadata", {}) if current_header is not None else {}
        )

        parent_agent_id = str(
            current_extra_payload.get("agent_id") or current_header_metadata.get("agent_id") or ""
        ).strip()
        parent_agent_name = str(
            current_extra_payload.get("agent_name")
            or current_header_metadata.get("agent_name")
            or ""
        ).strip()
        parent_conf_hash = str(current_header_metadata.get("conf_hash") or "").strip()
        parent_runtime_agent_type = str(getattr(context, "current_agent_id", "") or "").strip()

        delegate_parent_message_id = self._resolve_parent_message_id(context)

        parent_resume_target: dict[str, Any] = {
            "session_id": parent_session_id,
            "agent_id": parent_agent_id,
            "resume_via": "ResumeCommand.reply_data",
            "interrupt_reason": "AGENT_DELEGATE_WAIT",
        }
        if delegate_parent_message_id:
            parent_resume_target["delegate_parent_message_id"] = delegate_parent_message_id

        meta.setdefault("parent_resume_target", parent_resume_target)
        if delegate_parent_message_id:
            meta.setdefault("delegate_parent_message_id", delegate_parent_message_id)
        if parent_agent_id:
            meta.setdefault("resume_agent_id", parent_agent_id)
        if parent_agent_name:
            meta.setdefault("resume_agent_name", parent_agent_name)
        if parent_runtime_agent_type:
            meta.setdefault("resume_agent_type", parent_runtime_agent_type)
        if parent_conf_hash:
            meta.setdefault("resume_conf_hash", parent_conf_hash)

        parent_thread_id = str(getattr(context, "_langgraph_thread_id", "") or "")
        if parent_thread_id:
            meta.setdefault("resume_thread_id", parent_thread_id)

        return meta

    def _resolve_parent_message_id(self, context: Any) -> str:
        resolve_fn = getattr(context, "_resolve_delegate_parent_message_id", None)
        if callable(resolve_fn):
            try:
                result = resolve_fn()
                if result:
                    return str(result).strip()
            except Exception:
                logger.debug(
                    "DelegateToAgentTool: _resolve_delegate_parent_message_id failed",
                    exc_info=True,
                )
        return str(getattr(context, "message_id", "") or "").strip()

    def _build_call_agent_kwargs(
        self,
        *,
        resolved_content: str,
        message_id: str,
        context: Any,
        delegate_payload: dict[str, Any],
        delegate_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        call_kwargs: dict[str, Any] = {
            "target_agent_type": self.target_agent_type,
            "content": resolved_content,
            "wait_for_reply": True,
            "message_id": message_id,  # 稳定 ID，保证幂等
        }

        parent_message_id = self._resolve_parent_message_id(context)
        if parent_message_id:
            call_kwargs["parent_message_id"] = parent_message_id

        if delegate_payload:
            call_kwargs["payload"] = delegate_payload
        if delegate_metadata:
            call_kwargs["metadata"] = delegate_metadata

        return call_kwargs


def build_delegate_tool(
    *,
    target_agent_type: str,
    agent_name: str,
    agent_desc: str,
) -> DelegateToAgentTool:
    """工厂函数，供 Plugin 调用。"""
    return DelegateToAgentTool(
        name=target_agent_type,
        description=(
            f"Cross-agent delegate tool. Delegate to [{agent_name}]. "
            f"{agent_desc}\n"
            "`content` is the full task content to pass to target agent."
        ),
        target_agent_type=target_agent_type,
        agent_name=agent_name,
    )

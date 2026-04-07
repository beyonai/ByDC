"""DataCloud Gateway Worker."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import traceback
import uuid
from collections import OrderedDict
from collections.abc import Mapping

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from typing import Any

from by_framework import (
    AgentContext,
    AskUserEvent,
    EventType,
    GatewayCommand,
    GatewayWorker,
    ResumeCommand,
    StreamChunkEvent,
)
from by_framework.common.constants import (
    TASK_GROUP_FIELD_COMPLETED,
    TASK_GROUP_FIELD_TOTAL,
    TASK_GROUP_TTL_SECONDS,
    RedisKeys,
)
from by_framework.common.logger import logger
from by_framework.core.extensions import PluginRegistry
from by_framework.core.protocol.agent_state import AgentState as GatewayAgentState
from by_framework.core.protocol.agent_state import AgentStateLiteral, is_terminal_state
from by_framework.core.protocol.commands import AskAgentCommand
from by_framework.core.protocol.content_type import SseMessageType, SseReasonMessageType
from by_framework.core.protocol.events import StateChangeEvent
from datacloud_analysis.agent import create_agent
from datacloud_analysis.command_plugins import CommandPluginManager
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

_CHITCHAT_DIRECT_REPLY = "你好，我在。需要我帮你查询或分析什么数据？"
_CHITCHAT_TOKENS = {
    "hi",
    "hello",
    "hey",
    "thanks",
    "thank you",
    "你好",
    "您好",
    "喂",
    "哈喽",
    "在吗",
    "谢谢",
    "早上好",
    "中午好",
    "下午好",
    "晚上好",
}
_ANALYSIS_HINT_TOKENS = {
    "查",
    "查询",
    "分析",
    "统计",
    "报表",
    "销量",
    "销售",
    "订单",
    "数据",
    "多少",
    "趋势",
    "sql",
    "report",
    "query",
    "analy",
}

_NODE_THINKING_DESC: dict[str, str] = {
    "knowledge_enhance": "正在理解问题并补充上下文...\n\n",
    "planning": "正在生成任务计划...\n\n",
    "execution": "正在执行任务...\n\n",
    "end": "正在整理结果...",
}
_DEFAULT_THINKING_DESC = "正在处理，请稍候...\n\n"

_NODE_PHASE_TITLE: dict[str, str] = {
    "knowledge_enhance": "问题理解",
    "execution": "任务执行",
    "end": "结果生成",
}

_PLANNING_PHASE_TITLE = "任务生成"

_HEARTBEAT_INTERVAL: float = 3.0

_LOG_COMMAND_CONTENT_MAX_CHARS: int = 4000


def _truncate_for_command_log(value: Any, max_chars: int) -> Any:
    """Shorten long strings inside command dicts so a single log line stays usable."""

    if isinstance(value, str) and len(value) > max_chars:
        return "{0}...<truncated total_chars={1}".format(value[:max_chars], len(value))
    if isinstance(value, list):
        return [_truncate_for_command_log(item, max_chars) for item in value]
    if isinstance(value, dict):
        return {k: _truncate_for_command_log(v, max_chars) for k, v in value.items()}
    return value


def _json_line_for_console(obj: Any) -> str:
    """Serialize to one line using ASCII escapes (Windows GBK consoles cannot print some Unicode)."""

    try:
        return json.dumps(obj, ensure_ascii=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        return json.dumps(str(obj), ensure_ascii=True)


def _command_question_for_log(command: GatewayCommand) -> str:
    """Return body ``content`` (user question) as a log-safe string, matching AskAgent JSON ``body.content``."""

    raw = getattr(command, "content", None)
    if raw is None:
        return '""'
    if isinstance(raw, str):
        clipped = (
            raw
            if len(raw) <= _LOG_COMMAND_CONTENT_MAX_CHARS
            else "{0}...<truncated total_chars={1}>".format(
                raw[:_LOG_COMMAND_CONTENT_MAX_CHARS],
                len(raw),
            )
        )
        return json.dumps(clipped, ensure_ascii=True)
    truncated = _truncate_for_command_log(raw, _LOG_COMMAND_CONTENT_MAX_CHARS)
    return _json_line_for_console(truncated)


def _format_gateway_command_for_log(command: GatewayCommand) -> str:
    """Return one JSON line describing the gateway command (header + body)."""

    to_dict = getattr(command, "to_dict", None)
    if not callable(to_dict):
        return _json_line_for_console({"command_type": type(command).__name__, "error": "no_to_dict"})
    try:
        payload = to_dict()
    except Exception as exc:
        return _json_line_for_console(
            {"command_type": type(command).__name__, "to_dict_error": str(exc)}
        )
    truncated = _truncate_for_command_log(payload, _LOG_COMMAND_CONTENT_MAX_CHARS)
    return _json_line_for_console(truncated)


def _now_monotonic() -> float:
    return asyncio.get_running_loop().time()


async def _heartbeat_loop(
    context: AgentContext,
    stop_event: asyncio.Event,
    last_emit_time_ref: list[float],
) -> None:
    """Keep a silence watchdog alive without emitting frontend heartbeat text."""
    _ = context
    try:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
                break
            except TimeoutError:
                pass

            now = _now_monotonic()
            if now - last_emit_time_ref[0] < _HEARTBEAT_INTERVAL:
                continue
            last_emit_time_ref[0] = now
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("heartbeat loop exited with error: %s", exc)


def _compiled_graph_has_checkpointer(graph: Any) -> bool:
    """Return True if LangGraph was compiled with a usable checkpointer.

    ``Pregel.aget_state`` raises ``ValueError('No checkpointer set')`` when this is false.
    """

    cp = getattr(graph, "checkpointer", None)
    if cp is True:
        return True
    return isinstance(cp, BaseCheckpointSaver)


_no_checkpointer_logged: bool = False


class DataCloudWorker(GatewayWorker):
    """Worker that drives the datacloud-analysis graph inside the Gateway worker protocol."""

    _GRAPH_CACHE_MAX: int = 32
    _RESUME_RESULT_CACHE_MAX: int = 256

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        plugin_registry: PluginRegistry | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(plugin_registry=plugin_registry, *args, **kwargs)
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.graphs: OrderedDict = OrderedDict()
        self._resume_result_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._resume_inflight: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.command_plugin_manager = CommandPluginManager.from_defaults()

    def _build_resume_dedup_key(
        self,
        *,
        session_id: str,
        checkpoint_id: str,
        checkpoint_ns: str,
        resume_value: Any,
    ) -> str:
        try:
            resume_payload = json.dumps(
                resume_value, ensure_ascii=False, sort_keys=True, default=str
            )
        except Exception:
            resume_payload = repr(resume_value)
        raw = json.dumps(
            {
                "session_id": session_id,
                "checkpoint_id": checkpoint_id,
                "checkpoint_ns": checkpoint_ns,
                "resume_payload": resume_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _cache_resume_result(self, key: str, result: dict[str, Any]) -> None:
        self._resume_result_cache[key] = dict(result)
        self._resume_result_cache.move_to_end(key)
        while len(self._resume_result_cache) > self._RESUME_RESULT_CACHE_MAX:
            self._resume_result_cache.popitem(last=False)

    @staticmethod
    def _stringify_metadata_value(value: Any) -> str:
        return str(value or "").strip()

    def _resolve_runtime_agent_key(
        self,
        *,
        command: GatewayCommand,
        by_agent_id: Any,
        header_metadata: dict[str, Any],
    ) -> str:
        if isinstance(command, ResumeCommand):
            resume_agent_id = self._stringify_metadata_value(header_metadata.get("resume_agent_id"))
            if resume_agent_id:
                return resume_agent_id
            resume_agent_type = self._stringify_metadata_value(
                header_metadata.get("resume_agent_type")
            )
            if resume_agent_type:
                return resume_agent_type

        by_agent_text = self._stringify_metadata_value(by_agent_id)
        if by_agent_text:
            return by_agent_text
        target_agent_type = self._stringify_metadata_value(
            getattr(command.header, "target_agent_type", "")
        )
        if target_agent_type:
            return target_agent_type
        return self.worker_id

    @classmethod
    def _resolve_resume_checkpoint_target(
        cls,
        *,
        header_metadata: Mapping[str, Any],
    ) -> tuple[str, str]:
        resume_checkpoint_id = cls._stringify_metadata_value(
            header_metadata.get("resume_checkpoint_id")
        )
        resume_checkpoint_ns = cls._stringify_metadata_value(
            header_metadata.get("resume_checkpoint_ns")
        )
        plain_checkpoint_id = cls._stringify_metadata_value(header_metadata.get("checkpoint_id"))
        plain_checkpoint_ns = cls._stringify_metadata_value(header_metadata.get("checkpoint_ns"))
        resume_thread_id = cls._stringify_metadata_value(header_metadata.get("resume_thread_id"))

        if resume_checkpoint_id:
            return resume_checkpoint_id, resume_checkpoint_ns or plain_checkpoint_ns

        if resume_thread_id and plain_checkpoint_id:
            logger.warning(
                "ResumeCommand metadata contains resume_thread_id=%s but only plain checkpoint_id=%s; "
                "ignoring plain checkpoint_id and resuming from latest checkpoint on that thread",
                resume_thread_id,
                plain_checkpoint_id,
            )
            return "", ""

        return plain_checkpoint_id, plain_checkpoint_ns

    @classmethod
    def _build_thread_id(cls, *, session_id: str, agent_key: str) -> str:
        agent_text = cls._stringify_metadata_value(agent_key)
        session_text = cls._stringify_metadata_value(session_id)
        if not agent_text or not session_text:
            return session_text or agent_text
        return f"{agent_text}:{session_text}"

    @staticmethod
    def _is_internal_wait_result(process_result: Any, context: AgentContext) -> bool:
        if not getattr(context, "_is_suspended", False):
            return False
        if not isinstance(process_result, dict):
            return False
        return str(process_result.get("status") or "").strip().lower() == "waiting"

    async def _handle_message(
        self,
        command: GatewayCommand,
        cancel_event: asyncio.Event | None = None,
        cancel_reason: str = "",
        execution: Any | None = None,
    ) -> str:
        trace_id = uuid.uuid4().hex
        header = command.header

        is_agent_return = isinstance(command, ResumeCommand)
        source_agent_type = header.source_agent_type
        has_source_agent = bool(source_agent_type) and not is_agent_return
        workspace_dir = None

        context_parent_id = header.message_id
        if execution and execution.is_resumed and execution.existing_data:
            context_parent_id = execution.message_id or header.message_id

        context = AgentContext(
            session_id=header.session_id,
            trace_id=header.trace_id if header.trace_id else trace_id,
            redis_client=self.redis,
            current_agent_id=header.target_agent_type if header.target_agent_type else "",
            parent_message_id=context_parent_id,
            current_command=command,
            cancel_event=cancel_event,
            cancel_reason=cancel_reason,
            plugin_registry=self.plugin_registry,
            tenant_id=header.tenant_id,
            workspace_dir=workspace_dir,
            agent_configs=self.plugin_registry.agent_configs,
            storage=self.storage,
            is_sub_agent=has_source_agent,
        )
        if execution:
            execution.context = context
        process_result: Any = None

        logger.info(
            "[%s] Received message: %s (Trace: %s)",
            self.worker_id,
            header.message_id,
            trace_id,
        )
        logger.info("[%s] Target Agent Type: %s", self.worker_id, header.target_agent_type)
        logger.info("[%s] Session ID: %s", self.worker_id, header.session_id)

        token = None
        try:
            await self.plugin_registry.on_task_start(context)

            if not is_agent_return and hasattr(command, "content"):
                await context.agent_runtime_state.session_manager.history.save_message(
                    role="user",
                    content=command.content,
                    metadata={
                        "message_id": header.message_id,
                        "trace_id": header.trace_id,
                    },
                )

            logger.info(
                "[%s] Setting up workspace for session: %s", self.worker_id, header.session_id
            )
            paths = await self.workspace_manager.setup_workspace(
                header.session_id, header.message_id
            )
            logger.debug("[%s] Workspace paths: %s", self.worker_id, paths)

            if self.sandbox:
                logger.info("[%s] Installing sandbox", self.worker_id)
                self.sandbox.install()

            from by_framework.worker.sandbox.hook_sandbox import active_workspace  # noqa: PLC0415

            token = active_workspace.set(paths["private"])

            logger.info("[%s] Starting task processing", self.worker_id)
            if is_agent_return:
                await self._persist_agent_return_state(paths, command)

                if header.task_group_id:
                    group_key = RedisKeys.task_group(header.task_group_id)
                    results_key = RedisKeys.task_group_results(header.task_group_id)
                    total_str = await self.redis.hget(group_key, TASK_GROUP_FIELD_TOTAL)
                    if total_str is not None:
                        if isinstance(command, ResumeCommand):
                            result_data = {
                                "status": command.status,
                                "reply_data": command.reply_data,
                                "content": command.content,
                            }
                            await self.redis.hset(
                                results_key,
                                header.message_id,
                                json.dumps(result_data),
                            )
                            await self.redis.expire(results_key, TASK_GROUP_TTL_SECONDS)

                        completed = await self.redis.hincrby(
                            group_key, TASK_GROUP_FIELD_COMPLETED, 1
                        )
                        if completed < int(total_str):
                            logger.info(
                                "[%s] TaskGroup %s completed %d/%s, waiting...",
                                self.worker_id,
                                header.task_group_id,
                                completed,
                                total_str,
                            )
                            return f"{GatewayAgentState.QUEUED.value}: waiting_for_group"
                        logger.info(
                            "[%s] TaskGroup %s ALL COMPLETED (%s)!",
                            self.worker_id,
                            header.task_group_id,
                            total_str,
                        )

                await context.emit_state(StateChangeEvent(state=GatewayAgentState.RESUMED.value))

            process_result = await self.process_command(command, context)

            final_status = GatewayAgentState.COMPLETED.value
            if isinstance(process_result, dict) and "status" in process_result:
                final_status = str(process_result["status"])
            elif isinstance(process_result, str) and process_result in AgentStateLiteral.__args__:
                final_status = process_result

            if self._is_internal_wait_result(process_result, context):
                # wait_state = (
                #     GatewayAgentState.WAITING_AGENT.value
                #     if not is_agent_return
                #     else GatewayAgentState.RESUMED.value
                # )
                # await context.emit_state(StateChangeEvent(state=wait_state))
                # logger.info(
                #     "[%s] Task suspended internally with status=%s",
                #     self.worker_id,
                #     final_status,
                # )
                # await self.plugin_registry.on_task_complete(context, process_result)
                await context.flush_to_history()
                return final_status

            if has_source_agent:
                await self._enqueue_agent_return(
                    command,
                    status=GatewayAgentState.COMPLETED.value,
                    reply_data=process_result,
                )
                await context.emit_state(
                    StateChangeEvent(state=f"{GatewayAgentState.QUEUED.value}: {source_agent_type}")
                )
            else:
                await context.emit_state(StateChangeEvent(state=GatewayAgentState.COMPLETED.value))
            logger.info(
                "[%s] Task completed successfully with status: %s",
                self.worker_id,
                final_status,
            )
            await self.plugin_registry.on_task_complete(context, process_result)

            should_emit_stream_end = (
                not has_source_agent
                and is_terminal_state(final_status)
                and not getattr(context, "_permission_transferred", False)
                and not getattr(context, "_is_suspended", False)
            )
            if should_emit_stream_end:
                if not getattr(context, "_is_stream_finished", False):
                    await context.emit_chunk("", event_type=EventType.APP_STREAM_RESPONSE.value)
            else:
                await context.flush_to_history()

            return final_status

        except asyncio.CancelledError as e:
            logger.info("[%s] Task cancellation requested: %s", self.worker_id, str(e))
            await context.emit_state(StateChangeEvent(state=GatewayAgentState.CANCELLING.value))
            if has_source_agent:
                await self._enqueue_agent_return(
                    command,
                    status=GatewayAgentState.CANCELLED.value,
                    reply_data={"reason": str(e)},
                )
            await context.emit_state(StateChangeEvent(state=GatewayAgentState.CANCELLED.value))

            should_emit_stream_end = not has_source_agent and not getattr(
                context, "_permission_transferred", False
            )
            if should_emit_stream_end and not getattr(context, "_is_stream_finished", False):
                await context.emit_chunk("", event_type=EventType.APP_STREAM_RESPONSE.value)
            else:
                await context.flush_to_history()

            return GatewayAgentState.CANCELLED.value

        except Exception as e:
            error_msg = f"[{self.worker_id}] Task failed: {e!s}"
            logger.error(error_msg)
            if has_source_agent:
                await self._enqueue_agent_return(
                    command,
                    status=GatewayAgentState.FAILED.value,
                    reply_data={"error": str(e)},
                )
            await context.emit_state(
                StateChangeEvent(state=f"{GatewayAgentState.FAILED.value}: {e!s}")
            )
            logger.error(traceback.format_exc())
            await self.plugin_registry.on_task_error(context, e)

            should_emit_stream_end = not has_source_agent and not getattr(
                context, "_permission_transferred", False
            )
            if should_emit_stream_end and not getattr(context, "_is_stream_finished", False):
                await context.emit_chunk("", event_type=EventType.APP_STREAM_RESPONSE.value)
            else:
                await context.flush_to_history()

            return GatewayAgentState.FAILED.value
        finally:
            from by_framework.worker.sandbox.hook_sandbox import active_workspace  # noqa: PLC0415

            if token is not None:
                active_workspace.reset(token)
            if self.sandbox:
                logger.info("[%s] Uninstalling sandbox", self.worker_id)
                self.sandbox.uninstall()
            logger.info("[%s] Cleaning up task: %s", self.worker_id, header.message_id)
            await self.workspace_manager.cleanup_task(header.session_id, header.message_id)

    @staticmethod
    def _consume_future_exception(fut: asyncio.Future[dict[str, Any]]) -> None:
        if fut.cancelled():
            return
        try:
            fut.exception()
        except Exception:
            return

    def _build_graph(
        self,
        prompts_dict: dict | None = None,
        tools_dict: dict | None = None,
        mounted_objects: list[str] | None = None,  # 🆕 新增参数
    ) -> Any:
        """Instantiate the datacloud-analysis compiled graph with dynamic context."""
        return create_agent(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            prompts_overwrite=prompts_dict,
            tools=tools_dict,
            mounted_objects=mounted_objects,  # 🆕 传递 mounted_objects
        )

    async def start_heartbeat(self) -> None:
        await super().start_heartbeat()

        init_plugin = self.plugin_registry.get_plugin("datacloud_init_agent_conf")
        loaded_agent_ids = getattr(init_plugin, "loaded_agent_ids", []) if init_plugin else []
        if not loaded_agent_ids:
            raise RuntimeError("启动失败：未加载到任何数字员工配置。")
        logger.info(
            "Init plugin loaded digital employees: count=%d ids=%s",
            len(loaded_agent_ids),
            loaded_agent_ids,
        )

        # Set ontology scene path for knowledge injection middleware
        if not os.environ.get("DATACLOUD_ONTOLOGY_SCENE_PATH"):
            from pathlib import Path
            from datacloud_service.plugins.worker_plugins.init_agent_conf import _datacloud_repo_root

            repo_root = _datacloud_repo_root()
            scene_path = (
                repo_root
                / "examples"
                / "e_commerce_demo"
                / "mock_env"
                / "resource"
                / "knowledge"
                / "import_package_owl_onto"
            )
            if scene_path.exists():
                os.environ["DATACLOUD_ONTOLOGY_SCENE_PATH"] = str(scene_path)
                logger.info("DataCloudWorker: Set DATACLOUD_ONTOLOGY_SCENE_PATH=%s", scene_path)

        from datacloud_analysis import bootstrap

        await bootstrap.setup()

        logger.info("DataCloudWorker: SDK framework bootstrapped.")

    def get_capabilities(self) -> list[str]:
        """Capabilities registered by this worker."""
        return [os.environ.get("DATACLOUD_GATEWAY_WORKER_ID", "datacloud")]

    async def _emit_6001(self, context: AgentContext, payload: dict[str, Any]) -> None:
        """Emit one structured data-table JSON chunk (content_type=6001)."""
        data_table_type = getattr(SseMessageType, "data_table_json", None)
        content_type = data_table_type.value if data_table_type is not None else "6001"
        await context.emit_chunk(
            StreamChunkEvent(content=json.dumps(payload, ensure_ascii=False)),
            event_type=EventType.ANSWER_DELTA.value,
            content_type=content_type,
        )

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------

    async def process_command(self, command: GatewayCommand, context: AgentContext) -> dict:
        """Receive a command, run the graph, and stream events back to the caller.

        Handles two command types:
        - AskAgentCommand: fresh conversation turn, builds initial graph state.
        - ResumeCommand:   resumes a suspended graph via Command(resume=...).

        Returns:
            {"status": "done"}    normal completion, flush_to_history called.
            {"status": "waiting"} graph interrupted, ask_user emitted, no flush.
        """
        extra_payload = getattr(command, "extra_payload", {}) or {}
        header_metadata = getattr(getattr(command, "header", None), "metadata", None) or {}
        if isinstance(command, ResumeCommand):
            by_agent_id = (
                extra_payload.get("agent_id")
                or header_metadata.get("resume_agent_id")
                or header_metadata.get("agent_id")
            )
            by_agent_name = (
                extra_payload.get("agent_name")
                or header_metadata.get("resume_agent_name")
                or header_metadata.get("agent_name")
            )
        else:
            by_agent_id = extra_payload.get("agent_id") or header_metadata.get("agent_id")
            by_agent_name = extra_payload.get("agent_name") or header_metadata.get("agent_name")

        by_agent_name_log = json.dumps(
            "" if by_agent_name is None else str(by_agent_name),
            ensure_ascii=True,
        )

        logger.info(
            "DataCloudWorker.process_command: session=%s command_type=%s by_agent_id=%s "
            "by_agent_name=%s question=%s command=%s",
            context.session_id,
            type(command).__name__,
            by_agent_id,
            by_agent_name_log,
            _command_question_for_log(command),
            _format_gateway_command_for_log(command),
        )

        if self.api_key:
            os.environ["OPENAI_API_KEY"] = self.api_key
        if self.base_url:
            os.environ["OPENAI_BASE_URL"] = self.base_url
        if self.model_name:
            os.environ["DATACLOUD_LLM_REASONING_MODEL"] = self.model_name

        ext_params = extra_payload.get("ext_params")
        runtime_agent_key = self._resolve_runtime_agent_key(
            command=command,
            by_agent_id=by_agent_id,
            header_metadata=header_metadata,
        )
        logger.info(
            "Agent context: ID=%s (type=%s), Name=%s runtime_agent_key=%s",
            by_agent_id,
            type(by_agent_id).__name__,
            by_agent_name,
            runtime_agent_key,
        )

        resume_cache_key: str | None = None
        if isinstance(command, ResumeCommand):
            resume_value_probe = (
                command.reply_data if command.reply_data is not None else command.content
            )
            checkpoint_id_probe, checkpoint_ns_probe = self._resolve_resume_checkpoint_target(
                header_metadata=header_metadata
            )
            resume_cache_key = self._build_resume_dedup_key(
                session_id=context.session_id,
                checkpoint_id=checkpoint_id_probe,
                checkpoint_ns=checkpoint_ns_probe,
                resume_value=resume_value_probe,
            )
            cached = self._resume_result_cache.get(resume_cache_key)
            if cached is not None:
                logger.info(
                    "ResumeCommand idempotent hit: session=%s checkpoint_id=%s checkpoint_ns=%s",
                    context.session_id,
                    checkpoint_id_probe,
                    checkpoint_ns_probe,
                )
                self._resume_result_cache.move_to_end(resume_cache_key)
                return dict(cached)

        from by_framework.worker.sandbox.hook_sandbox import active_workspace  # noqa: PLC0415

        workspace_dir = active_workspace.get()
        logger.info("Active workspace for task: %s", workspace_dir)

        if isinstance(command, AskAgentCommand) and isinstance(ext_params, dict):
            handled, payload = await self.command_plugin_manager.handle_ext_command(
                ext_params=ext_params,
                session_id=context.session_id,
                workspace_dir=workspace_dir,
                gateway_context=context,
            )
            if handled:
                if payload is not None:
                    await self._emit_6001(context, payload)
                if not bool(ext_params.get("silent")):
                    await context.emit_chunk(
                        StreamChunkEvent(content="鍥炵瓟瀹屾垚"),
                        event_type=EventType.APP_STREAM_RESPONSE.value,
                        content_type=SseMessageType.text.value,
                    )
                    await context.flush_to_history()
                return {"status": "done"}

        if isinstance(command, AskAgentCommand):
            # 初始提示：第一层 sub_step(阶段标题)，第二层 emit_chunk(说明文本，路由到思考区)
            async with context.sub_step(_NODE_PHASE_TITLE["knowledge_enhance"]) as (m_id, p_id):
                await context.emit_chunk(
                    StreamChunkEvent(content="已接收到用户消息，开始处理"),
                    event_type=EventType.REASONING_LOG_START.value,
                    content_type=SseReasonMessageType.think_text.value,
                    message_id=m_id,
                    parent_message_id=p_id,
                )
            user_text = _latest_user_text_from_content(command.content)
            if _is_light_chitchat(user_text):
                await context.emit_chunk(
                    StreamChunkEvent(
                        content=_CHITCHAT_DIRECT_REPLY,
                        metadata={"graph_nodes_executed": 0},
                    ),
                    event_type=EventType.ANSWER_DELTA.value,
                    content_type=SseMessageType.text.value,
                )
                await context.emit_chunk(
                    StreamChunkEvent(content="鍥炵瓟瀹屾垚"),
                    event_type=EventType.APP_STREAM_RESPONSE.value,
                    content_type=SseMessageType.text.value,
                )
                await context.flush_to_history()
                return {"status": "done"}

        agent_configs = context.list_agent_configs()
        config_for_this_call = next(
            (cfg for cfg in agent_configs if str(cfg.agent_id) == str(by_agent_id)),
            None,
        )
        logger.info(
            "Agent config match result: by_agent_id=%s matched=%s",
            by_agent_id,
            bool(config_for_this_call),
        )
        tools_dict = getattr(config_for_this_call, "tools", None) or {}
        prompts_dict = getattr(config_for_this_call, "prompts", None) or {}
        config_extra = getattr(config_for_this_call, "extra", None) or {}
        tool_metadata = config_extra.get("tool_metadata", {})

        logger.info(
            "Agent config payload: agent_id=%s prompt_keys=%s tool_keys=%s",
            by_agent_id,
            sorted(str(key) for key in prompts_dict.keys()),
            sorted(str(key) for key in tools_dict.keys()),
        )

        # 🆕 从 extra 中提取 mounted_objects（优先），或从 tool_metadata 中提取（兼容旧逻辑）
        mounted_objects = []
        if "mounted_objects" in config_extra:
            mounted_objects = config_extra.get("mounted_objects", [])
            logger.info(
                "Agent config: agent_id=%s mounted_objects=%s (from extra)",
                by_agent_id,
                mounted_objects,
            )
        else:
            # 兼容旧逻辑：从 tool_metadata 中提取
            for tool_key, metadata in tool_metadata.items():
                resource_biz_type = metadata.get("resource_biz_type")
                resource_code = metadata.get("resource_code")
                if resource_biz_type in {"OBJECT", "VIEW"} and resource_code:
                    mounted_objects.append(resource_code)
            logger.info(
                "Agent config: agent_id=%s mounted_objects=%s (from tool_metadata)",
                by_agent_id,
                mounted_objects,
            )
        # 改动4: SkillsMiddleware 在运行时自动处理技能发现，无需在 worker 中手动加载
        logger.info(
            "Agent runtime tools: agent_id=%s tool_keys=%s",
            by_agent_id,
            sorted(str(key) for key in tools_dict),
        )

        # 🔍 打印工具的原始配置（用于诊断 mounted_objects 问题）
        logger.info("=" * 80)
        logger.info("WORKER: RAW TOOLS CONFIGURATION")
        logger.info("=" * 80)
        for tool_key, tool_value in tools_dict.items():
            logger.info("WORKER: tool_key=%s", tool_key)
            logger.info("WORKER:   type=%s", type(tool_value).__name__)
            if isinstance(tool_value, dict):
                logger.info("WORKER:   dict_keys=%s", list(tool_value.keys()))
                for k, v in tool_value.items():
                    if isinstance(v, str) and len(v) < 200:
                        logger.info("WORKER:     %s: %s", k, v)
                    else:
                        logger.info("WORKER:     %s: <%s>", k, type(v).__name__)
            elif hasattr(tool_value, "__dict__"):
                logger.info("WORKER:   attributes=%s", list(vars(tool_value).keys())[:10])
            logger.info("WORKER:   ---")
        logger.info("=" * 80)

        conf_payload = json.dumps(
            {"prompts": prompts_dict, "tool_keys": sorted(tools_dict.keys())},
            ensure_ascii=False,
            sort_keys=True,
        )
        computed_conf_hash = hashlib.sha1(conf_payload.encode("utf-8")).hexdigest()[:12]
        resume_conf_hash = ""
        if isinstance(command, ResumeCommand):
            resume_conf_hash = str(
                header_metadata.get("resume_conf_hash") or header_metadata.get("conf_hash") or ""
            ).strip()
            if resume_conf_hash and resume_conf_hash != computed_conf_hash:
                logger.warning(
                    "ResumeCommand conf_hash mismatch: metadata=%s computed=%s; "
                    "using metadata hash for cache affinity",
                    resume_conf_hash,
                    computed_conf_hash,
                )
        conf_hash = resume_conf_hash or computed_conf_hash
        cache_key = f"{by_agent_id}:{conf_hash}" if by_agent_id else f"default:{conf_hash}"

        target_graph = self.graphs.get(cache_key)
        if not target_graph:
            if config_for_this_call:
                target_graph = self._build_graph(
                    prompts_dict=prompts_dict,
                    tools_dict=tools_dict,
                    mounted_objects=mounted_objects,  # 🆕 传递 mounted_objects
                )
            else:
                logger.warning("AgentConfig for %s not found, fallback to defaults.", by_agent_id)
                target_graph = self._build_graph()
            self.graphs[cache_key] = target_graph
            while len(self.graphs) > self._GRAPH_CACHE_MAX:
                evicted_key, _ = self.graphs.popitem(last=False)
                logger.info("Graph cache evicted: key=%s", evicted_key)
        else:
            self.graphs.move_to_end(cache_key)

        thread_id = str(
            header_metadata.get("resume_thread_id") or header_metadata.get("thread_id") or ""
        ).strip()
        if not thread_id:
            thread_id = self._build_thread_id(
                session_id=context.session_id,
                agent_key=runtime_agent_key,
            )
        config = {
            "configurable": {
                "thread_id": thread_id,
                # DatacloudContext 字段平铺到 configurable（Deep Agents context_schema 要求）
                "gateway_context": context,
                "agent_id": str(by_agent_id or ""),
                "agent_name": str(by_agent_name or ""),
                "workspace_dir": workspace_dir,
                "session_id": context.session_id,
                "locale": str(getattr(context, "locale", "") or "zh_CN"),
                "trace_id": str(getattr(command.header, "trace_id", "") or ""),
            }
        }
        context._langgraph_thread_id = thread_id

        if isinstance(command, ResumeCommand):
            try:
                resume_payload_json = json.dumps(
                    command.to_dict(),
                    ensure_ascii=False,
                    default=str,
                )
            except Exception:
                resume_payload_json = repr(command)
            logger.info(
                "ResumeCommand received session=%s trace_id=%s payload=%s",
                context.session_id,
                getattr(command.header, "trace_id", ""),
                resume_payload_json,
            )
            resume_value = command.reply_data if command.reply_data is not None else command.content
            if isinstance(resume_value, str):
                resume_preview = resume_value[:500]
            else:
                try:
                    resume_preview = json.dumps(resume_value, ensure_ascii=False, default=str)[:500]
                except (TypeError, ValueError):
                    resume_preview = repr(resume_value)[:500]
            logger.info(
                "ResumeCommand: resume_value type=%s preview=%s",
                type(resume_value).__name__,
                resume_preview,
            )
            graph_input: Any = Command(resume=resume_value)
        else:
            latest_user_text = _latest_user_text_from_content(command.content)
            history_messages = await _load_recent_history_messages(
                context=context,
                limit=_history_inject_limit(),
                current_user_text=latest_user_text,
            )
            input_messages = _normalize_messages(command.content)
            # content 为 [] 或无法解析时，避免只有历史且最后一条为 assistant → intend 误用 AIMessage
            if not input_messages and latest_user_text:
                input_messages = [HumanMessage(content=latest_user_text)]
            combined_messages = history_messages + input_messages
            if _trace_user_query_enabled():
                raw_c = command.content
                c_extra = "type=%s" % type(raw_c).__name__
                if isinstance(raw_c, list):
                    c_extra += " list_len=%d" % len(raw_c)
                    if raw_c:
                        first = raw_c[0]
                        last = raw_c[-1]
                        c_extra += " first=%s last=%s" % (
                            list(first.keys()) if isinstance(first, dict) else type(first).__name__,
                            list(last.keys()) if isinstance(last, dict) else type(last).__name__,
                        )
                logger.info(
                    "[user_query_trace] worker graph_input.messages session=%s thread_id=%s "
                    "command.content %s",
                    context.session_id,
                    thread_id,
                    c_extra,
                )
                logger.info(
                    "[user_query_trace] worker graph_input.messages latest_user_text_len=%d "
                    "latest_preview=%r hist_n=%d input_n=%d combined_n=%d",
                    len(latest_user_text),
                    latest_user_text[:300] + ("..." if len(latest_user_text) > 300 else ""),
                    len(history_messages),
                    len(input_messages),
                    len(combined_messages),
                )
                for i, m in enumerate(combined_messages):
                    mt = type(m).__name__
                    mc = getattr(m, "content", "")
                    mp = (
                        mc[:200] + ("..." if isinstance(mc, str) and len(mc) > 200 else "")
                        if isinstance(mc, str)
                        else repr(mc)[:200]
                    )
                    logger.info("[user_query_trace] worker combined[%d] %s preview=%r", i, mt, mp)
            # 改动3: Deep Agents 架构下只传 messages；所有运行时上下文通过 config["configurable"] 注入
            graph_input = {
                "messages": combined_messages,
            }

        if isinstance(command, ResumeCommand):
            md = header_metadata
            ckpt_id, ckpt_ns = self._resolve_resume_checkpoint_target(header_metadata=md)
            if ckpt_id:
                config["configurable"]["checkpoint_id"] = ckpt_id
                config["configurable"]["checkpoint_ns"] = ckpt_ns
            logger.info(
                "ResumeCommand: langgraph thread_id=%s checkpoint_id=%s checkpoint_ns=%r "
                "(from header.metadata)",
                config["configurable"].get("thread_id", ""),
                config["configurable"].get("checkpoint_id", ""),
                config["configurable"].get("checkpoint_ns", ""),
            )

        resume_inflight_owner = False
        resume_inflight_future: asyncio.Future[dict[str, Any]] | None = None
        if isinstance(command, ResumeCommand) and resume_cache_key:
            inflight = self._resume_inflight.get(resume_cache_key)
            if inflight is not None:
                logger.info(
                    "ResumeCommand inflight hit: session=%s checkpoint_id=%s checkpoint_ns=%s",
                    context.session_id,
                    str(header_metadata.get("checkpoint_id") or ""),
                    str(header_metadata.get("checkpoint_ns") or ""),
                )
                inflight_result = await asyncio.shield(inflight)
                return dict(inflight_result)
            resume_inflight_owner = True
            resume_inflight_future = asyncio.get_running_loop().create_future()
            resume_inflight_future.add_done_callback(self._consume_future_exception)
            self._resume_inflight[resume_cache_key] = resume_inflight_future

        reco_task: asyncio.Task[list[str]] | None = None
        reco_plugin = (
            self.plugin_registry.get_plugin("datacloud_recommended_questions")
            if self.plugin_registry
            else None
        )
        if reco_plugin is not None and bool(getattr(reco_plugin.manifest, "enabled", True)):
            gen_fn = getattr(reco_plugin, "generate_recommended_questions", None)
            if callable(gen_fn):
                rq = _latest_user_text_from_content(command.content).strip()
                if rq:
                    reco_task = asyncio.create_task(gen_fn(rq))

        try:
            logger.info(
                "_stream_graph invoke session=%s input_is_command_resume=%s",
                context.session_id,
                isinstance(graph_input, Command),
            )
            stream_result = await self._stream_graph(
                target_graph=target_graph,
                graph_input=graph_input,
                config=config,
                context=context,
                by_agent_id=by_agent_id or "",
                conf_hash=conf_hash,
                reco_task=reco_task,
            )
            if isinstance(command, ResumeCommand) and resume_cache_key:
                self._cache_resume_result(resume_cache_key, stream_result)
            if (
                resume_inflight_owner
                and resume_inflight_future is not None
                and not resume_inflight_future.done()
            ):
                resume_inflight_future.set_result(dict(stream_result))
            return stream_result
        except Exception as exc:
            if (
                resume_inflight_owner
                and resume_inflight_future is not None
                and not resume_inflight_future.done()
            ):
                resume_inflight_future.set_exception(exc)
            raise
        finally:
            if resume_inflight_owner and resume_cache_key:
                self._resume_inflight.pop(resume_cache_key, None)

    async def _stream_graph(
        self,
        *,
        target_graph: Any,
        graph_input: Any,
        config: dict,
        context: AgentContext,
        by_agent_id: str,
        conf_hash: str,
        reco_task: asyncio.Task[list[str]] | None = None,
    ) -> dict:
        """Drive the graph stream and handle interrupt/done branches."""
        is_agent_delegate = False
        stream_event_count = 0
        phase_emitted: set[str] = set()
        last_emit_time_ref: list[float] = [_now_monotonic()]
        heartbeat_stop = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _heartbeat_loop(context, heartbeat_stop, last_emit_time_ref)
        )

        try:
            logger.info(
                "_stream_graph: astream_events begin session=%s conf_hash=%s",
                context.session_id,
                conf_hash,
            )
            async for event in target_graph.astream_events(
                graph_input, config=config, version="v2"
            ):
                stream_event_count += 1
                await context.check_cancelled()
                kind: str = str(event["event"])

                if kind == "on_chat_model_end":
                    node_name = str((event.get("metadata") or {}).get("langgraph_node") or "")
                    if node_name == "planning" and _PLANNING_PHASE_TITLE not in phase_emitted:
                        phase_emitted.add(_PLANNING_PHASE_TITLE)
                        async with context.sub_step(_PLANNING_PHASE_TITLE):
                            pass

                elif kind == "on_chain_end" and event.get("name") == "agent_delegate":
                    is_agent_delegate = True

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "")
                    tool_input = event.get("data", {}).get("input", {})
                    if tool_name:
                        step_title = f"调用工具: {tool_name}"
                        if step_title not in phase_emitted:
                            phase_emitted.add(step_title)
                            async with context.sub_step(step_title):
                                pass

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "")
                    if tool_name:
                        step_title = f"工具执行完成: {tool_name}"
                        if step_title not in phase_emitted:
                            phase_emitted.add(step_title)
                            async with context.sub_step(step_title):
                                pass

            logger.info(
                "_stream_graph: astream_events end session=%s event_count=%d",
                context.session_id,
                stream_event_count,
            )

            if _compiled_graph_has_checkpointer(target_graph):
                snapshot_config = {
                    "configurable": dict(config.get("configurable") or {}),
                }
                snapshot_config["configurable"].pop("checkpoint_id", None)
                snapshot = await target_graph.aget_state(snapshot_config)
            else:
                global _no_checkpointer_logged
                if not _no_checkpointer_logged:
                    logger.warning(
                        "Graph has no checkpointer: aget_state skipped, HITL/resume disabled. "
                        "Ensure bootstrap.setup() finished before the first create_agent(), "
                        "or clear graph cache if bootstrap order was wrong."
                    )
                    _no_checkpointer_logged = True
                snapshot = None

            ckpt_after = (
                snapshot.config.get("configurable", {}).get("checkpoint_id", "")
                if snapshot is not None
                else ""
            )
            logger.info(
                "_stream_graph: after aget_state session=%s snapshot_present=%s "
                "has_interrupts=%s checkpoint_id=%s",
                context.session_id,
                snapshot is not None,
                bool(snapshot.interrupts) if snapshot is not None else False,
                ckpt_after,
            )

            if snapshot is not None and snapshot.interrupts:
                first = snapshot.interrupts[0]
                interrupt_value = first.value
                interrupt_reason = "unknown_interrupt"
                if isinstance(interrupt_value, dict):
                    prompt = interrupt_value.get("prompt", str(interrupt_value))
                    interrupt_reason = str(
                        interrupt_value.get("reason_code")
                        or interrupt_value.get("interrupt_reason")
                        or "interrupt"
                    )
                else:
                    prompt = str(interrupt_value) if interrupt_value else "请补充您的回答。"
                    if prompt:
                        interrupt_reason = "prompt_interrupt"

                checkpoint_id = snapshot.config.get("configurable", {}).get("checkpoint_id", "")
                checkpoint_ns = snapshot.config.get("configurable", {}).get("checkpoint_ns", "")
                snapshot_values = snapshot.values if isinstance(snapshot.values, dict) else {}
                todo_active_id = str(snapshot_values.get("todo_active_id") or "")
                active_tools = snapshot_values.get("active_tools")
                pending_capability = ""
                if isinstance(active_tools, list) and active_tools:
                    pending_capability = str(active_tools[0] or "")
                if not pending_capability:
                    pending_capability = str(snapshot_values.get("target_tool") or "")

                logger.info(
                    "Graph interrupted: session=%s checkpoint_id=%s prompt=%r",
                    context.session_id,
                    checkpoint_id,
                    prompt,
                )
                if interrupt_reason == "AGENT_DELEGATE_WAIT":
                    # call_agent 已由 DelegateToAgentTool 基类（InterruptibleTool）在工具内部调用，
                    # worker 无需再处理，直接静默等待子 Agent 的 ResumeCommand 回调。
                    logger.info(
                        "_stream_graph: delegate wait interrupt, waiting for child agent resume "
                        "session=%s checkpoint_id=%s",
                        context.session_id,
                        checkpoint_id,
                    )
                    return {"status": "waiting"}
                await context.ask_user(
                    AskUserEvent(
                        prompt=prompt,
                        metadata={
                            "thread_id": config["configurable"]["thread_id"],
                            "checkpoint_id": checkpoint_id,
                            "checkpoint_ns": checkpoint_ns,
                            "agent_id": by_agent_id,
                            "conf_hash": conf_hash,
                            "todo_active_id": todo_active_id,
                            "react_step_id": todo_active_id,
                            "pending_capability": pending_capability,
                            "interrupt_reason": interrupt_reason,
                        },
                    )
                )
                await context.emit_chunk(
                    StreamChunkEvent(
                        content="回答完成",
                        metadata={
                            "relatedResources": _related_resources_from_reco_task(reco_task),
                        },
                    ),
                    event_type=EventType.APP_STREAM_RESPONSE.value,
                    content_type=SseMessageType.text.value,
                )
                logger.info("_stream_graph: return session=%s status=waiting", context.session_id)
                return {"status": "waiting"}

            # 从 snapshot 中提取最终的 AI 回复
            final_message = None
            if snapshot and snapshot.values:
                messages = snapshot.values.get("messages", [])
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage) and msg.content:
                        final_message = msg.content
                        break

            if not is_agent_delegate:
                # 普通模式：直接向前端推流
                if final_message:
                    logger.info(
                        "_stream_graph: sending final AI message session=%s content_length=%d",
                        context.session_id,
                        len(final_message),
                    )
                    await context.emit_chunk(
                        StreamChunkEvent(content=final_message),
                        event_type=EventType.ANSWER_DELTA.value,
                        content_type=SseMessageType.text.value,
                    )

                await context.emit_chunk(
                    StreamChunkEvent(
                        content="回答完成",
                        metadata={
                            "relatedResources": _related_resources_from_reco_task(reco_task),
                        },
                    ),
                    event_type=EventType.APP_STREAM_RESPONSE.value,
                    content_type=SseMessageType.text.value,
                )

            await context.flush_to_history()
            logger.info(
                "_stream_graph: return session=%s status=done conclusion_len=%d",
                context.session_id,
                len(final_message) if final_message else 0,
            )
            # conclusion 始终携带，父 Agent 恢复时可以从 reply_data 里取到结论文本
            return {"status": "done", "conclusion": final_message or ""}
        finally:
            heartbeat_stop.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            if reco_task is not None and not reco_task.done():
                reco_task.cancel()
                try:
                    await reco_task
                except asyncio.CancelledError:
                    pass


# ------------------------------------------------------------------

# ------------------------------------------------------------------


def _normalize_messages(
    content: Any,
) -> list[HumanMessage | AIMessage | SystemMessage]:
    """Convert gateway command content to a list of LangChain BaseMessage.

    Supports:
    """
    if isinstance(content, str):
        return [HumanMessage(content=content)]

    if not isinstance(content, list):
        return [HumanMessage(content=str(content))]

    messages: list[HumanMessage | AIMessage | SystemMessage] = []
    for item in content:
        if isinstance(item, dict) and "role" in item:
            role = item["role"]
            text = item.get("content", "")
            if role == "assistant":
                messages.append(AIMessage(content=text))
            elif role == "system":
                messages.append(SystemMessage(content=text))
            else:
                messages.append(HumanMessage(content=text))
        else:
            messages.append(HumanMessage(content=str(item)))

    return messages


def _trace_user_query_enabled() -> bool:
    """Set DATACLOUD_TRACE_USER_QUERY=1 to log graph message injection + intend resolution."""
    return os.environ.get("DATACLOUD_TRACE_USER_QUERY", "").strip().lower() in ("1", "true", "yes")


def _history_inject_limit() -> int:
    """How many recent DB history rows to merge into graph ``messages`` (Human/Assistant per row)."""
    raw = os.environ.get("DATACLOUD_HISTORY_MESSAGE_LIMIT", "12")
    try:
        n = int(raw.strip())
    except ValueError:
        return 12
    return max(1, min(n, 200))


async def _load_recent_history_messages(
    *,
    context: AgentContext,
    limit: int = 12,
    current_user_text: str = "",
) -> list[HumanMessage | AIMessage | SystemMessage]:
    """Load recent business history and convert to LangChain messages."""
    try:
        raw_history = await context.agent_runtime_state.session_manager.history.get_history(
            limit=limit
        )
    except Exception as exc:
        logger.warning("_load_recent_history_messages failed: %s", exc)
        return []

    if not isinstance(raw_history, list):
        return []

    history_messages: list[HumanMessage | AIMessage | SystemMessage] = []
    for item in raw_history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            history_messages.append(HumanMessage(content=content))
        elif role in {"assistant", "ai"}:
            history_messages.append(AIMessage(content=content))
        elif role == "system":
            history_messages.append(SystemMessage(content=content))

    popped_dup = False
    if current_user_text and history_messages:
        last_message = history_messages[-1]
        if (
            isinstance(last_message, HumanMessage)
            and str(last_message.content).strip() == current_user_text
        ):
            history_messages.pop()
            popped_dup = True

    if _trace_user_query_enabled():
        roles_in = []
        if isinstance(raw_history, list):
            for item in raw_history:
                if isinstance(item, dict):
                    roles_in.append(str(item.get("role") or "?"))
        logger.info(
            "[user_query_trace] history_load session=%s limit=%d raw_rows=%s roles_order=%s "
            "built_n=%d popped_dup_last_user=%s current_user_preview=%r",
            getattr(context, "session_id", ""),
            limit,
            len(raw_history) if isinstance(raw_history, list) else -1,
            roles_in,
            len(history_messages),
            popped_dup,
            current_user_text[:200] + ("..." if len(current_user_text) > 200 else ""),
        )

    return history_messages


def _related_resources_from_reco_task(task: asyncio.Task[list[str]] | None) -> list[str]:
    """Return LLM recommendations only if the background task already finished (no extra wait).

    This keeps tail latency unchanged: we never await an in-flight recommendation task at
    emit time; if the model finishes before the main graph, results are attached.
    """

    if task is None:
        return []
    if not task.done():
        return []
    try:
        out = task.result()
    except Exception as exc:
        logger.debug("recommendation task failed: %s", exc)
        return []
    if not isinstance(out, list):
        return []
    return [str(x).strip() for x in out if str(x).strip()]


def _latest_user_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list) or not content:
        return str(content).strip() if content is not None else ""
    last = content[-1]
    if isinstance(last, dict):
        raw = last.get("content", "")
        return raw.strip() if isinstance(raw, str) else str(raw).strip()
    return str(last).strip()


def _is_light_chitchat(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if not normalized:
        return False
    if any(token in normalized for token in _ANALYSIS_HINT_TOKENS):
        return False
    if normalized in _CHITCHAT_TOKENS:
        return True
    # Keep heuristic narrow to avoid hijacking real requests.
    return len(normalized) <= 10 and any(token in normalized for token in _CHITCHAT_TOKENS)

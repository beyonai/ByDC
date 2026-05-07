"""OntologyAgent — DataCloud SDK 公开 API（无 Gateway 中间层直调版本）。

设计文档：docs/概要设计/gateway解耦方案/dataCloud重构方案.md
"""

from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from datacloud_analysis.reporter import NoOpExecutionReporter

logger = logging.getLogger(__name__)

# ── 进程级图缓存上限（与 worker.py 原有 LRU 上限对齐） ──────────────────────
_CACHE_MAX: int = 32

# ── 事件模型 ─────────────────────────────────────────────────────────────────


class OntologyAgentEvent:
    """所有事件的基类，用于类型注解。"""


@dataclass
class ThinkingEvent(OntologyAgentEvent):
    """LLM 推理中的增量 token（来自非 respond 节点）。"""

    content: str


@dataclass
class StepEvent(OntologyAgentEvent):
    """执行阶段标题或思考过程片段（来自 dc_stream_chunk 自定义事件）。"""

    title: str
    detail: str | None = None


@dataclass
class InterruptEvent(OntologyAgentEvent):
    """图在此处暂停，调用方需处理后调用 resume()。"""

    thread_id: str
    reason: str  # "PARADIGM_CLARIFICATION" | "ASK_USER" | ...
    prompt: str
    paradigm_list: list[ParadigmGroup] | None = None


@dataclass
class AnswerEvent(OntologyAgentEvent):
    """最终答案（完整内容，一次性 yield）。"""

    content: str


@dataclass
class ErrorEvent(OntologyAgentEvent):
    """流异常终止。"""

    message: str
    code: str | None = None


# ── 维度选项模型 ──────────────────────────────────────────────────────────────


@dataclass
class ParadigmOption:
    choice_keyword: str
    recall: str


@dataclass
class ParadigmGroup:
    paradigm_id: str
    paradigm_name: str
    options: list[ParadigmOption] = field(default_factory=list)


@dataclass
class ParadigmGroupSelection:
    paradigm_id: str
    paradigm_name: str
    chosen_options: list[ParadigmOption] = field(default_factory=list)


@dataclass
class ParadigmAnswer:
    """用户选择的维度答案，传给 resume()。"""

    selections: list[ParadigmGroupSelection] = field(default_factory=list)


# ── 配置模型 ──────────────────────────────────────────────────────────────────


@dataclass
class OntologyAgentConfig:
    api_key: str
    model: str
    resource_path: str | Path
    base_url: str | None = None
    locale: str = "zh_CN"
    temperature: float = 0.7
    model_kwargs: dict[str, Any] | None = None
    # 结果文件存储后端（如 byclaw 的 ByclawResultFileStorage）。由调用方注入，
    # OntologyAgent 内不感知具体类型，仅透传给 configure_loader。
    result_file_storage: Any = None
    # HTTP_SQL 后端服务地址。非空时强制走 HttpSqlConnector 并注入此地址，
    # 取代历史的 DATACLOUD_SQL_SERVICE_URL 环境变量。
    sql_execute_url: str | None = None


# ── 缓存 key ──────────────────────────────────────────────────────────────────


def _make_cache_key(
    view_codes: list[str] | None,
    object_codes: list[str] | None,
) -> tuple[frozenset[str], frozenset[str]]:
    """构造图缓存 key，view/object 分属两个 frozenset 避免命名空间碰撞。"""
    return (frozenset(view_codes or []), frozenset(object_codes or []))


# ── 初始状态构建辅助 ──────────────────────────────────────────────────────────


def _build_input_payload(question: str) -> dict[str, Any]:
    """构建 AgentState 初始字段，与 runner.py 保持一致。"""
    from langchain_core.messages import HumanMessage  # noqa: PLC0415

    return {
        "messages": [HumanMessage(content=question)],
        "agent_id": None,
        "agent_name": None,
        "workspace_dir": None,
        "user_query": "",
        "enriched_query": "",
        "knowledge_payload": {},
        "term_hints": [],
        "knowledge_snippets": [],
        "thinking_log": {},
        "planning_input_source": "",
        "plan": [],
        "todos": [],
        "todo_md": "",
        "todo_md_path": "",
        "intent": None,
        "clarify_needed": False,
        "results": [],
        "execution_status": "",
        "todo_active_id": "",
        "todo_tool_plan": [],
        "active_tools": [],
        "execution_trace": [],
        "invocation_dedup": [],
        "final_answer": "",
        "artifact_refs": [],
        "execution_summary": None,
        "execution_summary_persistence": None,
        "resume_context": {},
        "query_mode": "analysis",
        "target_tool": "",
        "tool_params": {},
        "concept_terms": [],
        "confirmed_terms": [],
        "ambiguous_terms": [],
        "session_alias_map": {},
        "dynamic_tools": {},
        "prompts_overwrite": {},
        "planned_tasks": [],
        "task_queue": [],
        "results_list": [],
        "results_map": {},
        "final_summary": {},
    }


def _paradigm_answer_to_resume_value(answer: ParadigmAnswer) -> dict[str, Any]:
    """将 ParadigmAnswer 转换为 user_clarify_node 期望的 resume_value 格式。

    期望格式：{"paradigmList": [{"paradigmList": [{"choiceKeyword": ..., "recall": ...}]}]}
    """
    items: list[dict[str, str]] = []
    for sel in answer.selections:
        for opt in sel.chosen_options:
            items.append({"choiceKeyword": opt.choice_keyword, "recall": opt.recall})
    return {"paradigmList": [{"paradigmList": items}]}


def _interrupt_value_to_paradigm_list(
    ask_user_payload: dict[str, Any],
) -> list[ParadigmGroup] | None:
    """将 interrupt value 中的 paradigmList 解析为 list[ParadigmGroup]。"""
    raw_list = ask_user_payload.get("paradigmList") or []
    if not raw_list:
        return None

    groups: list[ParadigmGroup] = []
    for item in raw_list:
        paradigm_id = str(item.get("paradigmId") or item.get("paradigmCode") or "")
        paradigm_name = str(item.get("paradigmName") or "")
        raw_results = list(item.get("paradigmResult") or [])
        options: list[ParadigmOption] = [
            ParadigmOption(
                choice_keyword=str(r.get("choiceKeyword") or ""),
                recall=str(r.get("recall") or ""),
            )
            for r in raw_results
        ]
        groups.append(
            ParadigmGroup(
                paradigm_id=paradigm_id,
                paradigm_name=paradigm_name,
                options=options,
            )
        )
    return groups or None


# ── OntologyAgent ─────────────────────────────────────────────────────────────


class OntologyAgent:
    """DataCloud SDK 公开客户端，无需 Gateway 中间层即可直接发起问答。

    实例应长期持有（如应用启动时创建一次），以充分利用进程级图缓存（T6）。
    """

    def __init__(self, config: OntologyAgentConfig) -> None:
        self._config = config
        self._checkpointer = MemorySaver()
        # T6 进程级图缓存：OrderedDict 实现 LRU
        self._graph_cache: OrderedDict[tuple[frozenset[str], frozenset[str]], Any] = OrderedDict()

    # ── 公开 API ──────────────────────────────────────────────────────────────

    def ask(
        self,
        question: str,
        *,
        view_codes: list[str] | None = None,
        object_codes: list[str] | None = None,
        thread_id: str | None = None,
        user_code: str | None = None,
        session_id: str | None = None,
        locale: str | None = None,
        extras: dict[str, Any] | None = None,
    ) -> AsyncGenerator[OntologyAgentEvent, None]:
        """发起一次问答，流式返回事件。

        thread_id 使用规则：
          - 多轮对话：调用方自行生成（如 str(uuid.uuid4())）并在每轮传入相同值。
          - 一次性问答：传 None，SDK 内部生成，调用方无需保存。
          - 中断恢复：resume() 使用与本次 ask() 相同的 thread_id。

        user_code / session_id: datacloud 自己的请求级上下文字段。会被 OntologyAgent
        在内部组装成 duck-typed 容器并注入 LangGraph configurable，供下游
        tool_wrapper / HookAwareToolNode 通过 InvocationContext 透传至 SDK
        result_file_storage 等需要这两个字段的位置。本接口不感知 Gateway 概念。
        """
        effective_tid = thread_id or str(uuid.uuid4())
        return self._iter_events(
            question=question,
            view_codes=view_codes,
            object_codes=object_codes,
            thread_id=effective_tid,
            user_code=user_code,
            session_id=session_id,
            locale=locale,
            resume_input=None,
            extras=extras,
        )

    def resume(
        self,
        thread_id: str,
        user_input: str | ParadigmAnswer,
        *,
        view_codes: list[str] | None = None,
        object_codes: list[str] | None = None,
        user_code: str | None = None,
        session_id: str | None = None,
        extras: dict[str, Any] | None = None,
    ) -> AsyncGenerator[OntologyAgentEvent, None]:
        """在中断后恢复图执行，继续流式返回事件。

        view_codes / object_codes 须与触发中断的 ask() 保持一致。
        user_input:
          - str：文本回复（ASK_USER 场景）
          - ParadigmAnswer：维度选择（PARADIGM_CLARIFICATION 场景）
        user_code / session_id: 同 ask()。
        """
        return self._iter_events(
            question="",
            view_codes=view_codes,
            object_codes=object_codes,
            thread_id=thread_id,
            user_code=user_code,
            session_id=session_id,
            locale=None,
            resume_input=user_input,
            extras=extras,
        )

    # ── 内部实现 ──────────────────────────────────────────────────────────────

    def _build_loader(
        self,
        view_codes: list[str] | None,
        object_codes: list[str] | None,
    ) -> tuple[Any, list[str]]:
        """解析 OWL 文件，返回 (OntologyLoader, mounted_objects)。"""
        from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: PLC0415
        from datacloud_data_service.tools.virtual_action_injector import (  # noqa: PLC0415
            inject_virtual_actions,
        )

        from datacloud_analysis.tools.ontology_tool_loader import configure_loader  # noqa: PLC0415

        resource_path = Path(self._config.resource_path)
        loader = OntologyLoader()
        loader.load_from_owl_resource_directory(
            resource_path, object_codes=object_codes, view_codes=view_codes
        )

        # for view_code in view_codes or []:
        #     loader.load_view_with_deps(resource_path, view_code)
        # for obj_code in object_codes or []:
        #     loader.load_object_with_deps(resource_path, obj_code)

        inject_virtual_actions(loader)
        configure_loader(
            loader,
            model=self._config.model,
            api_key=self._config.api_key,
            base_url=self._config.base_url,
            temperature=self._config.temperature,
            result_file_storage=self._config.result_file_storage,
            sql_execute_url=self._config.sql_execute_url,
        )

        mounted = list(view_codes or []) + list(object_codes or [])
        return loader, mounted

    def _build_and_compile(
        self,
        view_codes: list[str] | None,
        object_codes: list[str] | None,
    ) -> Any:
        """构建并编译 LangGraph 图（无缓存层，供 T6 缓存逻辑调用）。"""
        from datacloud_analysis.orchestration.graph_builder import (  # noqa: PLC0415
            build_analysis_graph,
        )
        from datacloud_analysis.tools.ontology_tool_loader import (  # noqa: PLC0415
            OntologyToolLoader,
        )

        loader, mounted = self._build_loader(view_codes, object_codes)
        tools = OntologyToolLoader(mounted_objects=mounted, loader=loader).load()
        graph = build_analysis_graph(tools=tools, loader=loader)
        return graph.compile(checkpointer=self._checkpointer)

    def _get_or_build_graph(
        self,
        view_codes: list[str] | None,
        object_codes: list[str] | None,
    ) -> Any:
        """T6：带 LRU 缓存的图获取入口。"""
        key = _make_cache_key(view_codes, object_codes)
        if key in self._graph_cache:
            self._graph_cache.move_to_end(key)
            logger.debug("ontology_agent: graph cache hit key=%s", key)
            return self._graph_cache[key]

        logger.debug("ontology_agent: graph cache miss, building key=%s", key)
        compiled = self._build_and_compile(view_codes, object_codes)
        self._graph_cache[key] = compiled
        if len(self._graph_cache) > _CACHE_MAX:
            evicted = self._graph_cache.popitem(last=False)
            logger.debug("ontology_agent: evicted cache entry key=%s", evicted[0])
        return compiled

    async def _iter_events(  # type: ignore[return]
        self,
        *,
        question: str,
        view_codes: list[str] | None,
        object_codes: list[str] | None,
        thread_id: str,
        user_code: str | None,
        session_id: str | None,
        locale: str | None,
        resume_input: str | ParadigmAnswer | None,
        extras: dict[str, Any] | None = None,
    ) -> AsyncGenerator[OntologyAgentEvent, None]:
        """核心事件迭代器：构建图、执行、转换事件。"""
        try:
            compiled = self._get_or_build_graph(view_codes, object_codes)
        except Exception as exc:
            logger.exception("ontology_agent: failed to build graph")
            yield ErrorEvent(message=str(exc))
            return

        effective_locale = locale or self._config.locale
        # 无 Gateway 部署使用 NoOpExecutionReporter（实现 ExecutionReporter 协议），
        # 让 tool_wrapper.py 等业务代码不需感知是否有真实 Gateway。
        # 真实 Gateway（如 byclaw-data 的 AgentContext）走另一条路径直接被注入到
        # configurable["gateway_context"]，duck-type 自然满足同一协议。
        ctx_container: Any = NoOpExecutionReporter(
            user_id=user_code or "",
            session_id=session_id or "",
            extras=extras,
        )
        run_config: dict[str, Any] = {
            "configurable": {
                "thread_id": thread_id,
                "user_code": user_code,
                "gateway_context": ctx_container,
                "llm_config": {
                    "model": self._config.model,
                    "api_key": self._config.api_key,
                    "base_url": self._config.base_url,
                    "temperature": self._config.temperature,
                    "model_kwargs": self._config.model_kwargs,
                },
            }
        }

        if resume_input is None:
            graph_input: Any = _build_input_payload(question)
            graph_input["prompts_overwrite"] = {"locale": effective_locale}
        elif isinstance(resume_input, str):
            graph_input = Command(resume=resume_input)
        else:
            resume_value = _paradigm_answer_to_resume_value(resume_input)
            graph_input = Command(resume=resume_value)

        try:
            async for event in compiled.astream_events(
                graph_input,
                config=run_config,
                version="v2",
            ):
                event_type = event.get("event", "")
                metadata = event.get("metadata") or {}
                node = metadata.get("langgraph_node", "")

                if event_type == "on_chat_model_stream" and node != "respond":
                    chunk = (event.get("data") or {}).get("chunk")
                    content = getattr(chunk, "content", "") or ""
                    if content:
                        yield ThinkingEvent(content=content)

                elif event_type == "on_custom_event" and event.get("name") == "dc_stream_chunk":
                    data = event.get("data") or {}
                    text = str(data.get("content") or "").strip()
                    if text:
                        yield StepEvent(title=text)

        except Exception as exc:
            logger.exception("ontology_agent: stream error thread_id=%s", thread_id)
            yield ErrorEvent(message=str(exc))
            return

        # ── 流结束后检查是否中断 ────────────────────────────────────────────
        snapshot_config: dict[str, Any] = {"configurable": dict(run_config["configurable"].items())}
        snapshot_config["configurable"].pop("checkpoint_id", None)

        try:
            snapshot = await compiled.aget_state(snapshot_config)
        except Exception as exc:
            logger.exception("ontology_agent: aget_state failed thread_id=%s", thread_id)
            yield ErrorEvent(message=f"aget_state failed: {exc}")
            return

        if snapshot.interrupts:
            interrupt = snapshot.interrupts[0]
            iv = interrupt.value if hasattr(interrupt, "value") else interrupt
            reason_code = str((iv or {}).get("reason_code") or "UNKNOWN")
            prompt = str((iv or {}).get("prompt") or "")
            ask_payload: dict[str, Any] = dict((iv or {}).get("ask_user_payload") or {})
            paradigm_list = _interrupt_value_to_paradigm_list(ask_payload)

            yield InterruptEvent(
                thread_id=thread_id,
                reason=reason_code,
                prompt=prompt,
                paradigm_list=paradigm_list,
            )
            return

        final_answer = str(snapshot.values.get("final_answer") or "")
        yield AnswerEvent(content=final_answer)

    # 让 async generator 方法可被直接调用并返回 AsyncGenerator
    # _iter_events 是 async def + yield，Python 自动使其成为 async generator function。
    # ask()/resume() 直接 return self._iter_events(...)，此调用返回 AsyncGenerator 对象。

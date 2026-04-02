"""Initialize DataCloud agent configs and emit diagnostic logs."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx
from by_framework import AgentConfig, EventType, Plugin, PluginManifest, StreamChunkEvent
from by_framework.core.protocol.content_type import SseMessageType
from dotenv import load_dotenv

try:
    from datacloud_data_sdk.ontology.loader import OntologyLoader
    from datacloud_data_sdk.ontology.term_loader import TermLoader
    from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator
except ImportError:
    LangGraphPlanGenerator = None
    OntologyLoader = None
    TermLoader = None

logger = logging.getLogger(__name__)


class InitDataCloudDigitalEmployeePlugin(Plugin):
    """Load digital employee configs and dynamically build tools."""

    def __init__(self) -> None:
        super().__init__(
            manifest=PluginManifest(
                plugin_id="datacloud_init_agent_conf",
                version="1.0.0",
                priority=10,
                enabled=True,
            )
        )
        self.ai_factory_url = os.environ.get("AI_FACTORY_URL", "http://10.10.168.203:8569")
        self.ai_factory_token = os.environ.get("DATACLOUD_AI_FACTORY_TOKEN", "")
        self.loaded_agent_ids: list[str] = []
        repo_root = Path(__file__).resolve().parents[5]
        datacloud_data_env_path = repo_root / "packages" / "datacloud-data" / ".env"
        load_dotenv(datacloud_data_env_path)
        logger.info("[InitPlugin] Loaded datacloud-data env: path=%s", datacloud_data_env_path)

    @staticmethod
    def _default_workspace_dir() -> str:
        return str((Path(tempfile.gettempdir()) / "datacloud").resolve())

    @staticmethod
    def _is_ssl_verify_enabled() -> bool:
        raw = os.environ.get("DATACLOUD_AI_FACTORY_VERIFY_SSL", "false").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _agent_resource_ids_from_env() -> list[str]:
        """Read digital-employee resource id list from DATACLOUD_AI_FACTORY_AGENT_IDS."""

        raw = os.environ.get("DATACLOUD_AI_FACTORY_AGENT_IDS", "").strip()
        if not raw:
            raise ValueError(
                "DATACLOUD_AI_FACTORY_AGENT_IDS is not set. "
                "Set a JSON array such as [\"10000587\",\"10000582\"]."
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"DATACLOUD_AI_FACTORY_AGENT_IDS must be valid JSON: {exc}"
            ) from exc
        if not isinstance(parsed, list):
            raise TypeError("DATACLOUD_AI_FACTORY_AGENT_IDS must be a JSON array.")

        ids = [str(x).strip() for x in parsed if str(x).strip()]
        if not ids:
            raise ValueError("DATACLOUD_AI_FACTORY_AGENT_IDS parsed to an empty list.")
        return ids

    async def register_agent_configs(self, agent_context: Any) -> list[AgentConfig]:
        """Load digital-employee configs and return merged AgentConfig list."""

        current_map = {cfg.agent_id: cfg for cfg in agent_context.list_agent_configs()}
        loaded_agent_ids: list[str] = []
        failed_agent_ids: list[str] = []
        empty_tool_agent_ids: list[str] = []

        logger.info(
            "[InitPlugin] Start loading digital employees: base_url=%s token_configured=%s",
            self.ai_factory_url,
            bool(self.ai_factory_token),
        )

        agent_ids = self._agent_resource_ids_from_env()
        logger.info(
            "[InitPlugin] Agent resource ids from env: count=%d ids=%s",
            len(agent_ids),
            agent_ids,
        )
        if not self.ai_factory_token:
            raise ValueError("DATACLOUD_AI_FACTORY_TOKEN is not set.")

        headers = {
            "Content-Type": "application/json",
            "Beyond-Token": self.ai_factory_token,
        }
        verify_ssl = self._is_ssl_verify_enabled()
        try:
            async with httpx.AsyncClient(verify=verify_ssl) as client:
                for agent_id in agent_ids:
                    detail_resp = await client.post(
                        f"{self.ai_factory_url}/byaiService/digitalEmployeeController/findDetailsById",
                        json={"resourceId": agent_id, "language": "zh-CN"},
                        headers=headers,
                    )
                    if detail_resp.status_code != 200:
                        failed_agent_ids.append(agent_id)
                        logger.warning(
                            "[InitPlugin] Failed to fetch detail: agent_id=%s status_code=%s body=%s",
                            agent_id,
                            detail_resp.status_code,
                            detail_resp.text,
                        )
                        continue

                    payload = detail_resp.json()
                    if payload.get("code") != 0:
                        failed_agent_ids.append(agent_id)
                        logger.warning(
                            "[InitPlugin] Failed to fetch detail: agent_id=%s code=%s body=%s",
                            agent_id,
                            payload.get("code"),
                            detail_resp.text,
                        )
                        continue

                    did_load = self._handle_single_agent_detail(
                        current_map=current_map,
                        agent_id=str(agent_id),
                        detail_data=payload.get("data", {}) or {},
                        empty_tool_agent_ids=empty_tool_agent_ids,
                    )
                    if did_load:
                        loaded_agent_ids.append(str(agent_id))
        except Exception:
            logger.exception("[InitPlugin] Failed to load dynamic agent configs")

        self.loaded_agent_ids = loaded_agent_ids
        logger.info(
            "[InitPlugin] Load result: loaded=%d failed=%d loaded_agent_ids=%s",
            len(loaded_agent_ids),
            len(failed_agent_ids),
            loaded_agent_ids,
        )
        if empty_tool_agent_ids:
            raise RuntimeError(
                f"Startup failed: no tools for agents {', '.join(empty_tool_agent_ids)}"
            )
        if not loaded_agent_ids:
            raise RuntimeError("Startup failed: no digital employee config loaded.")
        return list(current_map.values())

    def _handle_single_agent_detail(
        self,
        *,
        current_map: dict[Any, AgentConfig],
        agent_id: str,
        detail_data: dict[str, Any],
        empty_tool_agent_ids: list[str],
    ) -> bool:
        dynamic_prompts = {
            "system_prompt": detail_data.get("resourceDesc", ""),
            "task_prompt": self._compile_task_prompt(detail_data),
        }
        prompt_preview = {key: str(value)[:200] for key, value in dynamic_prompts.items()}

        rel_resource_list = detail_data.get("relResourceList") or []
        if not isinstance(rel_resource_list, list):
            rel_resource_list = []
        dynamic_tools, build_diag = self._build_dynamic_tools_with_diagnostics(
            agent_id=agent_id,
            rel_resource_list=rel_resource_list,
        )
        tool_names = sorted(dynamic_tools.keys())
        reason_summary = list(build_diag.get("reason_summary") or [])

        logger.info(
            "[InitPlugin] Agent loaded: agent_id=%s prompt_keys=%s tool_count=%d tool_names=%s",
            agent_id,
            sorted(dynamic_prompts.keys()),
            len(tool_names),
            tool_names,
        )
        logger.info(
            "[InitPlugin] Agent prompt preview: agent_id=%s prompts=%s",
            agent_id,
            prompt_preview,
        )
        if reason_summary:
            logger.warning(
                "[InitPlugin] Tool diagnostic summary: agent_id=%s reasons=%s",
                agent_id,
                reason_summary,
            )
        if not tool_names:
            empty_tool_agent_ids.append(agent_id)
            logger.error(
                "[InitPlugin] Agent has no tools: agent_id=%s tool_count=0 reason_summary=%s",
                agent_id,
                reason_summary,
            )
            return False

        current_map[agent_id] = AgentConfig(
            agent_id=agent_id,
            tools=dynamic_tools,
            prompts=dynamic_prompts,
            skills={},
            on_conflict="overwrite",
        )
        self._save_offline_cache(agent_id, detail_data)
        return True

    @staticmethod
    def _compile_task_prompt(detail: dict[str, Any]) -> str:
        parts: list[str] = []
        parts.append(f"{detail['corePersonaDefinition']}")
        return "\n\n".join(parts)

    @staticmethod
    def _rel_resource_snapshot(rel: dict[str, Any]) -> dict[str, str]:
        return {
            "resourceBizType": str(rel.get("resourceBizType") or ""),
            "resourceType": str(rel.get("resourceType") or ""),
            "resourceCode": str(rel.get("resourceCode") or ""),
            "resourceName": str(rel.get("resourceName") or ""),
        }

    def _build_dynamic_tools_with_diagnostics(
        self,
        *,
        agent_id: str,
        rel_resource_list: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        rel_summaries = [self._rel_resource_snapshot(rel) for rel in rel_resource_list]
        logger.info(
            "[InitPlugin][ToolLoad][Input] agent_id=%s rel_count=%d rel_resources=%s",
            agent_id,
            len(rel_summaries),
            rel_summaries,
        )

        ontology_candidates: list[dict[str, str]] = []
        delegate_candidates: list[dict[str, str]] = []
        filtered_resources: list[dict[str, Any]] = []
        for rel in rel_resource_list:
            snapshot = self._rel_resource_snapshot(rel)
            biz_type = snapshot["resourceBizType"]
            if biz_type in {"OBJECT", "VIEW"}:
                ontology_candidates.append(snapshot)
            elif biz_type == "AGENT":
                delegate_candidates.append(snapshot)
            else:
                filtered_resources.append({**snapshot, "reason": "condition_mismatch_filtered"})

        logger.info(
            "[InitPlugin][ToolLoad][Classify] agent_id=%s ontology_candidates=%d delegate_candidates=%d "
            "filtered=%d filtered_resources=%s",
            agent_id,
            len(ontology_candidates),
            len(delegate_candidates),
            len(filtered_resources),
            filtered_resources,
        )

        ontology_tools, ontology_report = self._build_ontology_tools_with_diagnostics(
            agent_id=agent_id,
            rel_resource_list=rel_resource_list,
        )
        delegate_tools, delegate_report = self._build_delegate_tools_with_diagnostics(
            agent_id=agent_id,
            rel_resource_list=rel_resource_list,
        )
        collisions = sorted(set(ontology_tools) & set(delegate_tools))
        merged_tools = {**ontology_tools, **delegate_tools}

        reason_summary: list[str] = []
        if not rel_resource_list:
            reason_summary.append("upstream_rel_resource_list_empty")
        if filtered_resources:
            reason_summary.append(f"condition_mismatch_filtered:{len(filtered_resources)}")
        if ontology_report["failed"]:
            reason_summary.append(f"ontology_build_failed:{len(ontology_report['failed'])}")
        if delegate_report["failed"]:
            reason_summary.append(f"delegate_build_failed:{len(delegate_report['failed'])}")
        if collisions:
            reason_summary.append(f"tool_name_collision_overwritten_by_delegate:{','.join(collisions)}")
        if not merged_tools:
            reason_summary.append("final_dynamic_tools_empty")

        logger.info(
            "[InitPlugin][ToolLoad][Final] agent_id=%s ontology_tools=%s delegate_tools=%s merged_tools=%s "
            "tool_count=%d reason_summary=%s",
            agent_id,
            sorted(ontology_tools),
            sorted(delegate_tools),
            sorted(merged_tools),
            len(merged_tools),
            reason_summary,
        )
        return merged_tools, {
            "rel_resources": rel_summaries,
            "ontology_candidates": ontology_candidates,
            "delegate_candidates": delegate_candidates,
            "filtered_resources": filtered_resources,
            "ontology_report": ontology_report,
            "delegate_report": delegate_report,
            "collisions": collisions,
            "reason_summary": reason_summary,
        }

    def _build_ontology_tools_with_diagnostics(
        self,
        *,
        agent_id: str,
        rel_resource_list: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        report: dict[str, list[dict[str, Any]]] = {"built": [], "failed": [], "skipped": []}
        tools: dict[str, Any] = {}

        if not rel_resource_list:
            report["skipped"].append({"reason": "upstream_rel_resource_list_empty"})
            return tools, report
        if not (OntologyLoader and LangGraphPlanGenerator and TermLoader):
            report["skipped"].append({"reason": "ontology_sdk_unavailable"})
            logger.warning("[InitPlugin][ToolLoad][Ontology] agent_id=%s skip: sdk unavailable", agent_id)
            return tools, report

        for rel in rel_resource_list:
            state, item, new_tools = self._build_single_ontology_resource(
                agent_id=agent_id,
                rel=rel,
            )
            report[state].append(item)
            if state == "built":
                tools.update(new_tools)

        logger.info(
            "[InitPlugin][ToolLoad][OntologySummary] agent_id=%s built=%d failed=%d skipped=%d tool_count=%d "
            "tool_keys=%s",
            agent_id,
            len(report["built"]),
            len(report["failed"]),
            len(report["skipped"]),
            len(tools),
            sorted(tools),
        )
        return tools, report

    def _build_single_ontology_resource(
        self,
        *,
        agent_id: str,
        rel: dict[str, Any],
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        snapshot = self._rel_resource_snapshot(rel)
        resource_code = snapshot["resourceCode"]
        resource_biz_type = snapshot["resourceBizType"]
        resource_type = snapshot["resourceType"]

        state = "skipped"
        item: dict[str, Any] = {**snapshot, "reason": "condition_mismatch_filtered"}
        created: dict[str, Any] = {}
        if resource_biz_type not in {"OBJECT", "VIEW"}:
            return state, item, created
        if not resource_code:
            return "skipped", {**snapshot, "reason": "missing_resource_code"}, created

        try:
            loader = OntologyLoader()
            scene_path = self._resolve_scene_path(rel)
            if not scene_path:
                return "skipped", {**snapshot, "reason": "scene_path_unresolved"}, created

            loader.load_from_owl_directory(scene_path)
            loader.configure(
                plan_generator=LangGraphPlanGenerator(
                    model=os.environ.get("DATACLOUD_LLM_CODING_MODEL", "Qwen/Qwen3-235B-A22B"),
                    base_url=os.environ.get("OPENAI_BASE_URL"),
                    api_key=os.environ.get("OPENAI_API_KEY"),
                    temperature=0.0,
                ),
                term_loader=TermLoader.from_config({}),
                csv_base_dir=os.environ.get(
                    "DATACLOUD_GATEWAY_WORKSPACE_DIR", self._default_workspace_dir()
                ),
                sql_execution_mode="internal",
            )

            created, missing_reason = self._build_ontology_resource_tools(
                loader=loader,
                rel=rel,
                resource_code=resource_code,
                resource_biz_type=resource_biz_type,
                resource_type=resource_type,
            )
            if missing_reason:
                return "skipped", {**snapshot, "reason": missing_reason}, {}

            if created:
                logger.info(
                    "[InitPlugin][ToolLoad][Ontology] agent_id=%s build_ok resource_code=%s tool_keys=%s",
                    agent_id,
                    resource_code,
                    sorted(created),
                )
                state = "built"
                item = {**snapshot, "tool_keys": sorted(created)}
            else:
                item = {**snapshot, "reason": "matched_but_no_tool_generated"}
        except Exception as exc:
            logger.warning(
                "[InitPlugin][ToolLoad][Ontology] agent_id=%s build_failed resource=%s err=%s",
                agent_id,
                snapshot,
                exc,
            )
            state = "failed"
            item = {**snapshot, "reason": "matched_but_build_failed", "error": str(exc)}

        return state, item, created

    def _build_ontology_resource_tools(
        self,
        *,
        loader: Any,
        rel: dict[str, Any],
        resource_code: str,
        resource_biz_type: str,
        resource_type: str,
    ) -> tuple[dict[str, Any], str | None]:
        if resource_biz_type == "OBJECT":
            return self._build_object_tools(
                loader=loader,
                rel=rel,
                resource_code=resource_code,
                resource_type=resource_type,
            )
        return self._build_view_tools(
            loader=loader,
            rel=rel,
            resource_code=resource_code,
        )

    def _build_object_tools(
        self,
        *,
        loader: Any,
        rel: dict[str, Any],
        resource_code: str,
        resource_type: str,
    ) -> tuple[dict[str, Any], str | None]:
        obj = loader.get_object(resource_code)
        if obj is None:
            return {}, "object_not_found"

        tools: dict[str, Any] = {}
        if resource_type in {"api", "DB_TABLE"}:
            for act_code in obj.list_action_codes():
                tools[act_code] = obj.get_action_schema(act_code)
        if resource_type == "DB_TABLE":
            tool_name = f"{resource_code}_query"
            tools[tool_name] = self._build_query_tool(
                obj.query,
                tool_name=tool_name,
                tool_desc=f"{rel.get('resourceName', resource_code)} {rel.get('resourceDesc', '')}".strip(),
            )
        return tools, None

    def _build_view_tools(
        self,
        *,
        loader: Any,
        rel: dict[str, Any],
        resource_code: str,
    ) -> tuple[dict[str, Any], str | None]:
        view = loader.get_view(resource_code)
        if view is None:
            return {}, "view_not_found"

        tool_name = f"{resource_code}_query"
        return {
            tool_name: self._build_query_tool(
                view.query,
                tool_name=tool_name,
                tool_desc=f"{rel.get('resourceName', resource_code)} {rel.get('resourceDesc', '')}".strip(),
            )
        }, None

    def _build_delegate_tools_with_diagnostics(
        self,
        *,
        agent_id: str,
        rel_resource_list: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        report: dict[str, list[dict[str, Any]]] = {"built": [], "failed": [], "skipped": []}
        tools: dict[str, Any] = {}
        if not rel_resource_list:
            report["skipped"].append({"reason": "upstream_rel_resource_list_empty"})
            return tools, report

        for rel in rel_resource_list:
            snapshot = self._rel_resource_snapshot(rel)
            resource_code = snapshot["resourceCode"]
            if snapshot["resourceBizType"] != "AGENT":
                report["skipped"].append({**snapshot, "reason": "condition_mismatch_filtered"})
                continue
            if not resource_code:
                report["skipped"].append({**snapshot, "reason": "missing_resource_code"})
                continue
            try:
                resource_name = str(rel.get("resourceName") or resource_code)
                resource_desc = str(rel.get("resourceDesc") or "")
                tools[resource_code] = self._build_agent_delegate_tool(
                    target_agent_type=resource_code,
                    agent_name=resource_name,
                    agent_desc=resource_desc,
                )
                report["built"].append({**snapshot, "tool_keys": [resource_code]})
                logger.info(
                    "[InitPlugin][ToolLoad][Delegate] agent_id=%s build_ok resource_code=%s tool_key=%s",
                    agent_id,
                    resource_code,
                    resource_code,
                )
            except Exception as exc:
                report["failed"].append(
                    {**snapshot, "reason": "matched_but_build_failed", "error": str(exc)}
                )
                logger.warning(
                    "[InitPlugin][ToolLoad][Delegate] agent_id=%s build_failed resource=%s err=%s",
                    agent_id,
                    snapshot,
                    exc,
                )

        logger.info(
            "[InitPlugin][ToolLoad][DelegateSummary] agent_id=%s built=%d failed=%d skipped=%d tool_count=%d "
            "tool_keys=%s",
            agent_id,
            len(report["built"]),
            len(report["failed"]),
            len(report["skipped"]),
            len(tools),
            sorted(tools),
        )
        return tools, report

    def _build_query_tool(
        self,
        query_func: Any,
        *,
        tool_name: str,
        tool_desc: str = "",
    ) -> Any:
        """Wrap query(question=...) into a dispatcher-compatible async callable."""

        async def _tool(**params: Any) -> Any:
            question = (
                params.get("question") or params.get("query") or params.get("description") or ""
            )
            return await query_func(question=str(question), include_plan=True)

        _tool.__doc__ = (
            f"Query tool: {tool_name}. {tool_desc}\n"
            "Params: question/query/description (one of them)."
        )
        return _tool

    def _build_agent_delegate_tool(
        self,
        *,
        target_agent_type: str,
        agent_name: str,
        agent_desc: str,
    ) -> Any:
        """Build a tool that delegates to another agent via context.call_agent."""

        async def _tool(content: str | None = None, _context: Any = None, **params: Any) -> Any:
            # 恢复路径：execution_node 将子 agent 结果注入 inputs["__delegate_result__"]
            delegate_result = params.get("__delegate_result__")
            if delegate_result is not None:
                return delegate_result

            resolved_content = str(
                content
                or params.get("content")
                or params.get("question")
                or params.get("query")
                or params.get("description")
                or ""
            ).strip()
            if not resolved_content:
                resolved_content = f"Please handle request related to {agent_name}."

            if _context is None:
                logger.error(
                    "[AgentDelegate] context missing, cannot delegate: target=%s",
                    target_agent_type,
                )
                return f"Error: missing runtime context for delegated agent {agent_name}."

            raw_delegate_policy = params.get("delegate_policy")
            delegate_policy = (
                dict(raw_delegate_policy) if isinstance(raw_delegate_policy, dict) else {}
            )
            delegate_mode = str(delegate_policy.get("mode") or "").strip().lower()
            wait_for_reply = bool(delegate_policy.get("wait_for_reply"))
            sync_wait = not delegate_policy or delegate_mode == "sync" or wait_for_reply

            raw_payload = params.get("payload")
            delegate_payload = dict(raw_payload) if isinstance(raw_payload, dict) else {}
            raw_metadata = params.get("metadata")
            delegate_metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}

            parent_session_id = str(getattr(_context, "session_id", "") or "").strip()
            current_command = getattr(_context, "current_command", None)
            current_extra_payload = (
                getattr(current_command, "extra_payload", {}) if current_command is not None else {}
            )
            current_header = getattr(current_command, "header", None)
            current_header_metadata = (
                getattr(current_header, "metadata", {}) if current_header is not None else {}
            )
            parent_agent_id = str(
                current_extra_payload.get("agent_id")
                or current_header_metadata.get("agent_id")
                or ""
            ).strip()
            parent_agent_name = str(
                current_extra_payload.get("agent_name")
                or current_header_metadata.get("agent_name")
                or ""
            ).strip()
            parent_conf_hash = str(current_header_metadata.get("conf_hash") or "").strip()
            parent_runtime_agent_type = str(getattr(_context, "current_agent_id", "") or "").strip()
            parent_resume_target = {
                "session_id": parent_session_id,
                "agent_id": parent_agent_id,
                "resume_via": "ResumeCommand.reply_data",
                "interrupt_reason": "AGENT_DELEGATE_WAIT",
            }
            delegate_metadata.setdefault("parent_resume_target", parent_resume_target)
            if parent_agent_id:
                delegate_metadata.setdefault("resume_agent_id", parent_agent_id)
            if parent_agent_name:
                delegate_metadata.setdefault("resume_agent_name", parent_agent_name)
            if parent_runtime_agent_type:
                delegate_metadata.setdefault("resume_agent_type", parent_runtime_agent_type)
            if parent_conf_hash:
                delegate_metadata.setdefault("resume_conf_hash", parent_conf_hash)
            # 将父 agent 的 thread_id 传给子 agent，子 agent 回调时带回，
            # 确保 ResumeCommand 能找到正确的 LangGraph checkpoint
            parent_thread_id = str(getattr(_context, "_langgraph_thread_id", "") or "")
            if parent_thread_id:
                delegate_metadata.setdefault("resume_thread_id", parent_thread_id)

            delegate_message_id = ""
            generate_message_id = getattr(_context, "generate_message_id", None)
            if callable(generate_message_id):
                try:
                    delegate_message_id = str(generate_message_id() or "").strip()
                except Exception:
                    logger.debug(
                        "[AgentDelegate] generate_message_id failed for target=%s",
                        target_agent_type,
                        exc_info=True,
                    )

            delegate_parent_message_id = ""
            resolve_delegate_parent_message_id = getattr(
                _context,
                "_resolve_delegate_parent_message_id",
                None,
            )
            if callable(resolve_delegate_parent_message_id):
                try:
                    delegate_parent_message_id = str(
                        resolve_delegate_parent_message_id() or ""
                    ).strip()
                except Exception:
                    logger.debug(
                        "[AgentDelegate] resolve delegate parent message id failed for target=%s",
                        target_agent_type,
                        exc_info=True,
                    )
            if not delegate_parent_message_id:
                delegate_parent_message_id = str(
                    getattr(_context, "message_id", "") or ""
                ).strip()

            call_agent_kwargs: dict[str, Any] = {
                "target_agent_type": target_agent_type,
                "content": resolved_content,
                # wait_for_reply=True 只负责注册回调路由；父图是否继续由 interrupt 控制。
                "wait_for_reply": True,
            }
            if delegate_message_id:
                call_agent_kwargs["message_id"] = delegate_message_id
            if delegate_parent_message_id:
                call_agent_kwargs["parent_message_id"] = delegate_parent_message_id
            if delegate_payload:
                call_agent_kwargs["payload"] = delegate_payload
            if delegate_metadata:
                call_agent_kwargs["metadata"] = delegate_metadata

            logger.info(
                "[AgentDelegate] delegating: target=%s sync_wait=%s content=%.100s",
                target_agent_type,
                sync_wait,
                resolved_content,
            )

            if sync_wait:
                await _context.call_agent(**call_agent_kwargs)
                # 不在 tool 内部 interrupt，返回标记让 execution_node 在顶层统一处理
                return {
                    "__delegate_wait__": True,
                    "target_agent_type": target_agent_type,
                    "target_agent_name": agent_name,
                    "delegate_content": resolved_content,
                }

            await _context.emit_chunk(
                StreamChunkEvent(
                    content=f"Delegating request to agent [{agent_name}]:\n\n{resolved_content}"
                ),
                event_type=EventType.ANSWER_DELTA.value,
                content_type=SseMessageType.text.value,
            )
            await _context.call_agent(**call_agent_kwargs)
            return f"Request has been delegated to [{agent_name}]."

        _tool.__doc__ = (
            f"Cross-agent delegate tool. Delegate to [{agent_name}]. "
            f"{agent_desc}\n"
            "`content` is the full task content to pass to target agent."
        )
        _tool._is_agent_delegate = True  # type: ignore[attr-defined]
        return _tool

    def _resolve_scene_path(self, rel: dict[str, Any]) -> str:
        """Resolve ontology scene path for local test mode."""

        repo_root = Path(__file__).resolve().parents[5]
        fixed_scene_dir = (
            repo_root
            / "examples"
            / "e_commerce_demo"
            / "mock_env"
            / "resource"
            / "knowledge"
            / "import_package_owl_onto"
        )
        if fixed_scene_dir.exists():
            logger.info(
                "[InitPlugin] Using fixed scene path for test: path=%s rel_resource_code=%s",
                str(fixed_scene_dir),
                rel.get("resourceCode"),
            )
            return str(fixed_scene_dir)
        return ""

    def _save_offline_cache(self, agent_id: str, detail_data: dict[str, Any]) -> None:
        base_dir = os.environ.get("DATACLOUD_GATEWAY_WORKSPACE_DIR", self._default_workspace_dir())
        cache_dir = Path(base_dir) / "agent_configs"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / f"agent_{agent_id}.json"
            with cache_file.open("w", encoding="utf-8") as handle:
                json.dump(detail_data, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Cache save warning: %s", exc)

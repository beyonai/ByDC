"""初始化 dataCloud agent config，并输出加载结果。"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from by_framework import AgentConfig, EventType, Plugin, PluginManifest, StreamChunkEvent
from by_framework.core.protocol.content_type import SseMessageType

# 尝试导入本体加载相关模块，处理关联实体工具的动态生成
try:
    from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator
    from datacloud_data_sdk.ontology.term_loader import TermLoader
    from datacloud_data_sdk.ontology.loader import OntologyLoader
except ImportError:
    LangGraphPlanGenerator = None
    TermLoader = None
    OntologyLoader = None

logger = logging.getLogger(__name__)


class InitDataCloudDigitalEmployeePlugin(Plugin):
    """动态拉取并初始化注册平台级数字员工配置包。"""

    def __init__(self):
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
    def _agent_resource_ids_from_env() -> list[str]:
        """Read digital-employee resourceId list from ``DATACLOUD_AI_FACTORY_AGENT_IDS``.

        The variable must be a JSON array (string elements or coercible to str), e.g.
        ``["10000587","10000582"]``.

        Returns:
            Non-empty list of resource id strings.

        Raises:
            ValueError: If unset, invalid JSON, or empty after parsing.
            TypeError: If JSON value is not an array.
        """

        raw = os.environ.get("DATACLOUD_AI_FACTORY_AGENT_IDS", "").strip()
        if not raw:
            msg = (
                "DATACLOUD_AI_FACTORY_AGENT_IDS is not set. "
                'Set a JSON array of resourceId strings, e.g. ["10000587","10000582"].'
            )
            raise ValueError(msg)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"DATACLOUD_AI_FACTORY_AGENT_IDS must be valid JSON: {e}"
            ) from e
        if not isinstance(parsed, list):
            raise TypeError("DATACLOUD_AI_FACTORY_AGENT_IDS must be a JSON array.")
        ids = [str(x).strip() for x in parsed if str(x).strip()]
        if not ids:
            raise ValueError("DATACLOUD_AI_FACTORY_AGENT_IDS parsed to an empty list.")
        return ids

    async def register_agent_configs(self, agent_context):
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

        try:
            # 1. 从环境变量读取待加载的 resourceId 列表（不再请求 getResourceListByPage）
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

            async with httpx.AsyncClient(verify=False) as client:
                for agent_id in agent_ids:
                    # 2. 通过 resourceId 请求 /findDetailsById 详情
                    res_detail = await client.post(
                        f"{self.ai_factory_url}/byaiService/digitalEmployeeController/findDetailsById",
                        json={"resourceId": agent_id, "language": "zh-CN"},
                        headers=headers,
                    )

                    if res_detail.status_code == 200 and res_detail.json().get("code") == 0:
                        detail_data = res_detail.json().get("data", {})

                        # 3. 将性格、属性等五大维度合并重构为 Task Prompt
                        compiled_prompt = self._compile_task_prompt(detail_data)
                        dynamic_prompts = {
                            "system_prompt": detail_data.get("resourceDesc", ""),
                            "task_prompt": compiled_prompt,
                        }
                        prompt_preview = {
                            key: str(value)[:200] for key, value in dynamic_prompts.items()
                        }

                        # 4. 构建工具：本体工具 + Agent 委托工具（含全链路诊断）
                        rel_resource_list = detail_data.get("relResourceList", [])
                        dynamic_tools, build_diag = self._build_dynamic_tools_with_diagnostics(
                            agent_id=str(agent_id),
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
                                "[InitPlugin] Agent has no tools: agent_id=%s tool_count=0 tool_names=%s "
                                "reason_summary=%s",
                                agent_id,
                                tool_names,
                                reason_summary,
                            )
                            continue

                        # 5. 组装产生 AgentConfig，存入上下文 Map
                        current_map[agent_id] = AgentConfig(
                            agent_id=agent_id,
                            tools=dynamic_tools,
                            prompts=dynamic_prompts,
                            skills={},
                            on_conflict="overwrite",
                        )

                        # 可选：落盘机制
                        self._save_offline_cache(agent_id, detail_data)
                        loaded_agent_ids.append(agent_id)
                    else:
                        failed_agent_ids.append(agent_id)
                        logger.warning(
                            "[InitPlugin] Failed to fetch detail: agent_id=%s status_code=%s body=%s",
                            agent_id,
                            res_detail.status_code,
                            res_detail.text,
                        )
        except Exception as e:
            logger.exception("[InitPlugin] Failed to load dynamic agent configs: %s", e)

        self.loaded_agent_ids = loaded_agent_ids
        logger.info(
            "[InitPlugin] Load result: loaded=%d failed=%d loaded_agent_ids=%s",
            len(loaded_agent_ids),
            len(failed_agent_ids),
            loaded_agent_ids,
        )
        if empty_tool_agent_ids:
            raise RuntimeError(
                f"启动失败：以下数字员工未挂载任何工具：{', '.join(empty_tool_agent_ids)}"
            )

        if not loaded_agent_ids:
            raise RuntimeError("启动失败：未加载到任何数字员工配置")

        return list(current_map.values())

    def _compile_task_prompt(self, detail: dict) -> str:
        """合并不停的属性配置拼装成大段 context 约束。"""
        parts = []
        if detail.get("roleAttributes"):
            parts.append(f"【角色属性】\n{detail['roleAttributes']}")
        if detail.get("processingFlow"):
            parts.append(f"【处理流程】\n{detail['processingFlow']}")
        if detail.get("personalityDimensions"):
            parts.append(f"【性格维度】\n{detail['personalityDimensions']}")
        if detail.get("wordPreferences"):
            parts.append(f"【用词偏好】\n{detail['wordPreferences']}")
        if detail.get("sentenceAndTone"):
            parts.append(f"【句式与语气】\n{detail['sentenceAndTone']}")

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
                filtered_resources.append(
                    {
                        **snapshot,
                        "reason": "condition_mismatch_filtered",
                    }
                )

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
        collisions = sorted(set(ontology_tools.keys()) & set(delegate_tools.keys()))
        merged_tools = {**ontology_tools, **delegate_tools}

        reason_summary: list[str] = []
        if not rel_resource_list:
            reason_summary.append("upstream_rel_resource_list_empty")
        if filtered_resources:
            reason_summary.append(f"condition_mismatch_filtered:{len(filtered_resources)}")
        if len(ontology_report.get("failed", [])) > 0:
            reason_summary.append(f"ontology_build_failed:{len(ontology_report['failed'])}")
        if len(delegate_report.get("failed", [])) > 0:
            reason_summary.append(f"delegate_build_failed:{len(delegate_report['failed'])}")
        if collisions:
            reason_summary.append(f"tool_name_collision_overwritten_by_delegate:{','.join(collisions)}")
        if not merged_tools:
            reason_summary.append("final_dynamic_tools_empty")

        logger.info(
            "[InitPlugin][ToolLoad][Final] agent_id=%s ontology_tools=%s delegate_tools=%s merged_tools=%s "
            "tool_count=%d reason_summary=%s",
            agent_id,
            sorted(ontology_tools.keys()),
            sorted(delegate_tools.keys()),
            sorted(merged_tools.keys()),
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
        report: dict[str, Any] = {"built": [], "failed": [], "skipped": []}
        tools: dict[str, Any] = {}
        if not rel_resource_list:
            report["skipped"].append({"reason": "upstream_rel_resource_list_empty"})
            return tools, report
        if not OntologyLoader:
            report["skipped"].append({"reason": "ontology_loader_unavailable"})
            logger.warning(
                "[InitPlugin][ToolLoad][Ontology] agent_id=%s skip: OntologyLoader unavailable",
                agent_id,
            )
            return tools, report

        for rel in rel_resource_list:
            snapshot = self._rel_resource_snapshot(rel)
            resource_code = snapshot["resourceCode"]
            resource_biz_type = snapshot["resourceBizType"]
            resource_type = snapshot["resourceType"]

            if resource_biz_type not in {"OBJECT", "VIEW"}:
                report["skipped"].append({**snapshot, "reason": "condition_mismatch_filtered"})
                continue
            if not resource_code:
                report["skipped"].append({**snapshot, "reason": "missing_resource_code"})
                continue

            created_tool_keys: list[str] = []
            try:
                loader = OntologyLoader()
                scene_path = self._resolve_scene_path(rel)
                if not scene_path:
                    report["skipped"].append({**snapshot, "reason": "scene_path_unresolved"})
                    continue

                loader.load_from_owl_directory(scene_path)
                loader.configure(
                    plan_generator=LangGraphPlanGenerator(
                        model=os.environ.get("DATACLOUD_LLM_REASONING_MODEL", "Qwen/Qwen3-235B-A22B"),
                        base_url=os.environ.get("OPENAI_BASE_URL"),
                        api_key=os.environ.get("OPENAI_API_KEY"),
                        temperature=0.0,
                    ),
                    term_loader=TermLoader.from_config({}),
                    csv_base_dir=os.environ.get(
                        "DATACLOUD_GATEWAY_WORKSPACE_DIR", str(Path("/tmp/datacloud").resolve())
                    ),
                    sql_execution_mode="internal",
                )

                if resource_biz_type == "OBJECT":
                    obj = loader.get_object(resource_code)
                    if obj is None:
                        report["skipped"].append({**snapshot, "reason": "object_not_found"})
                        continue
                    if resource_type in {"api", "DB_TABLE"}:
                        for act_code in obj.list_action_codes():
                            tools[act_code] = obj.get_action_schema(act_code)
                            created_tool_keys.append(act_code)
                    if resource_type == "DB_TABLE":
                        query_tool_name = f"{resource_code}_query"
                        tools[query_tool_name] = self._build_query_tool(
                            obj.query,
                            tool_name=query_tool_name,
                            tool_desc=f"{rel.get('resourceName', resource_code)} {rel.get('resourceDesc', '')}".strip(),
                        )
                        created_tool_keys.append(query_tool_name)

                elif resource_biz_type == "VIEW":
                    view = loader.get_view(resource_code)
                    if view is None:
                        report["skipped"].append({**snapshot, "reason": "view_not_found"})
                        continue
                    query_tool_name = f"{resource_code}_query"
                    tools[query_tool_name] = self._build_query_tool(
                        view.query,
                        tool_name=query_tool_name,
                        tool_desc=f"{rel.get('resourceName', resource_code)} {rel.get('resourceDesc', '')}".strip(),
                    )
                    created_tool_keys.append(query_tool_name)

                if created_tool_keys:
                    report["built"].append({**snapshot, "tool_keys": created_tool_keys})
                    logger.info(
                        "[InitPlugin][ToolLoad][Ontology] agent_id=%s build_ok resource_code=%s tool_keys=%s",
                        agent_id,
                        resource_code,
                        created_tool_keys,
                    )
                else:
                    report["skipped"].append({**snapshot, "reason": "matched_but_no_tool_generated"})
            except Exception as exc:
                report["failed"].append(
                    {
                        **snapshot,
                        "reason": "matched_but_build_failed",
                        "error": str(exc),
                    }
                )
                logger.warning(
                    "[InitPlugin][ToolLoad][Ontology] agent_id=%s build_failed resource=%s err=%s",
                    agent_id,
                    snapshot,
                    exc,
                )

        logger.info(
            "[InitPlugin][ToolLoad][OntologySummary] agent_id=%s built=%d failed=%d skipped=%d tool_count=%d "
            "tool_keys=%s",
            agent_id,
            len(report["built"]),
            len(report["failed"]),
            len(report["skipped"]),
            len(tools),
            sorted(tools.keys()),
        )
        return tools, report

    def _build_delegate_tools_with_diagnostics(
        self,
        *,
        agent_id: str,
        rel_resource_list: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        report: dict[str, Any] = {"built": [], "failed": [], "skipped": []}
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
                    {
                        **snapshot,
                        "reason": "matched_but_build_failed",
                        "error": str(exc),
                    }
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
            sorted(tools.keys()),
        )
        return tools, report

    def _build_tools_from_ontology(self, rel_resource_list: list) -> dict:
        """基于本体加载工具。"""
        if not rel_resource_list or not OntologyLoader:
            return {}

        dynamic_tools = {}
        for rel in rel_resource_list:
            if rel.get("resourceBizType") in ["OBJECT", "VIEW"]:
                try:
                    loader = OntologyLoader()
                    scene_path = self._resolve_scene_path(rel)
                    if not scene_path:
                        continue

                    # loader.load_from_path(scene_path)
                    # loader.load_scene_from_path(scene_path)
                    loader.load_from_owl_directory(scene_path)

                    # 使用环境变量摒弃硬编码
                    loader.configure(
                        plan_generator=LangGraphPlanGenerator(
                            model=os.environ.get(
                                "DATACLOUD_LLM_REASONING_MODEL", "Qwen/Qwen3-235B-A22B"
                            ),
                            base_url=os.environ.get("OPENAI_BASE_URL"),
                            api_key=os.environ.get("OPENAI_API_KEY"),
                            temperature=0.0,
                        ),
                        term_loader=TermLoader.from_config({}),
                        csv_base_dir=os.environ.get(
                            "DATACLOUD_GATEWAY_WORKSPACE_DIR", str(Path("/tmp/datacloud").resolve())
                        ),
                        sql_execution_mode="internal",
                    )

                    resource_code = rel.get("resourceCode")
                    resource_biz_type = rel.get("resourceBizType")
                    resource_type = rel.get("resourceType")

                    if resource_biz_type == "OBJECT":
                        obj = loader.get_object(resource_code)
                        if obj:
                            # 1、2 规则：无论是 api 还是 DB_TABLE，都需要先加载他们列出来的动作 schema
                            if resource_type in ["api", "DB_TABLE"]:
                                for act_code in obj.list_action_codes():
                                    dynamic_tools[act_code] = obj.get_action_schema(act_code)

                            # 当资源类型为 DB_TABLE 时，额外补充自身的 query() 动态工具
                            if resource_type == "DB_TABLE":
                                dynamic_tools[f"{resource_code}_query"] = self._build_query_tool(
                                    obj.query,
                                    tool_name=f"{resource_code}_query",
                                    tool_desc=f"{rel.get('resourceName', resource_code)} {rel.get('resourceDesc', '')}".strip(),
                                )

                    elif resource_biz_type == "VIEW":
                        view = loader.get_view(resource_code)
                        if view:
                            # 3：当作为 VIEW 挂载时，补充 view.query()
                            dynamic_tools[f"{resource_code}_query"] = self._build_query_tool(
                                view.query,
                                tool_name=f"{resource_code}_query",
                                tool_desc=f"{rel.get('resourceName', resource_code)} {rel.get('resourceDesc', '')}".strip(),
                            )
                except Exception as e:
                    logger.warning("本体解析失败 rel=%s err=%s", rel, e)
        return dynamic_tools

    def _build_query_tool(self, query_func, *, tool_name: str, tool_desc: str = ""):
        """Wrap query(question=...) into a dispatcher-compatible async callable."""

        async def _tool(**params):
            question = (
                params.get("question") or params.get("query") or params.get("description") or ""
            )
            return await query_func(question=str(question), include_plan=True)

        _tool.__doc__ = (
            f"查询工具：{tool_name}。"
            f"{tool_desc}\n"
            "参数：question/query/description（三选一，均表示查询语句）。"
        )
        return _tool

    def _build_agent_delegate_tools(self, rel_resource_list: list) -> dict:
        """为 resourceBizType=AGENT 的关联资源构建跨进程委托工具。"""
        tools = {}
        for rel in rel_resource_list:
            if rel.get("resourceBizType") != "AGENT":
                continue
            resource_code = rel.get("resourceCode", "")
            if not resource_code:
                continue
            resource_name = rel.get("resourceName", resource_code)
            resource_desc = rel.get("resourceDesc", "")
            tools[resource_code] = self._build_agent_delegate_tool(
                target_agent_type=resource_code,
                agent_name=resource_name,
                agent_desc=resource_desc,
            )
        return tools

    def _build_agent_delegate_tool(self, target_agent_type: str, agent_name: str, agent_desc: str):
        """Build a tool that delegates to another agent via context.call_agent."""

        async def _tool(content: str | None = None, _context=None, **params):
            resolved_content = str(
                content
                or params.get("content")
                or params.get("question")
                or params.get("query")
                or params.get("description")
                or ""
            ).strip()
            if not resolved_content:
                resolved_content = f"请处理与「{agent_name}」相关的问题。"
            if _context is None:
                logger.error(
                    "[AgentDelegate] 运行时 context 未注入，无法调度 Agent: target=%s",
                    target_agent_type,
                )
                return f"错误：无法获取运行时 context，无法调度 Agent【{agent_name}】"

            logger.info(
                "[AgentDelegate] 正在调度 Agent: target=%s content=%.100s",
                target_agent_type,
                resolved_content,
            )
            await _context.emit_chunk(
                StreamChunkEvent(content=f"正在将以下请求移交给专项Agent【{agent_name}】处理：\n\n{resolved_content}"),
                event_type=EventType.ANSWER_DELTA.value,
                content_type=SseMessageType.text.value,
            )
            await _context.call_agent(
                target_agent_type=target_agent_type,
                content=resolved_content,
                wait_for_reply=False,
            )
            # import asyncio
            # await asyncio.sleep(60)  # 小延迟，确保事件及时发送
            return f"已将任务移交给【{agent_name}】处理。"

        _tool.__doc__ = (
            f"【跨进程Agent调用】：调度专项Agent【{agent_name}】处理任务。"
            f"{agent_desc}\n`content` 为要传递给目标Agent的完整任务内容。"
        )
        _tool._is_agent_delegate = True  # 供路由层识别
        return _tool

    def _resolve_scene_path(self, rel: dict) -> str:
        """Resolve scene path for temporary local testing."""
        repo_root = Path(__file__).resolve().parents[5]
        fixed_scene_file = (
            repo_root
            / "examples"
            / "e_commerce_demo"
            / "mock_env"
            / "resource"
            / "knowledge"
            / "import_package_owl_onto"
        )
        if fixed_scene_file.exists():
            logger.info(
                "[InitPlugin] Using fixed scene path for test: path=%s rel_resource_code=%s",
                str(fixed_scene_file),
                rel.get("resourceCode"),
            )
            return str(fixed_scene_file)
        return ""

    def _save_offline_cache(self, agent_id: str, detail_data: dict):
        base_dir = os.environ.get("DATACLOUD_GATEWAY_WORKSPACE_DIR", "/tmp/datacloud")
        cache_dir = Path(base_dir) / "agent_configs"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / f"agent_{agent_id}.json"
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(detail_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Cache save warning: %s", e)

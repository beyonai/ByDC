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
from langgraph.types import interrupt

try:
    from datacloud_data_sdk.ontology.loader import OntologyLoader
    from datacloud_data_sdk.ontology.term_loader import TermLoader
    from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator
except ImportError:
    LangGraphPlanGenerator = None
    OntologyLoader = None
    TermLoader = None

logger = logging.getLogger(__name__)

# 环境变量名称常量
ENV_ONTOLOGY_PATH = "DATACLOUD_ONTOLOGY_PATH"
ENV_DISABLE_SSL_VERIFY = "DATACLOUD_DISABLE_SSL_VERIFY"


def _datacloud_repo_root() -> Path:
    """Resolve whale_datacloud repo root (contains ``packages/datacloud-data/``)."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages" / "datacloud-data").is_dir():
            return parent

    # 回退：查找 .git 或 pyproject.toml
    for parent in here.parents:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent

    # 最后回退：返回当前文件的根目录
    logger.warning("Cannot find repo root, using file parent directory")
    return here.parent


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
        self.ai_factory_url = os.environ.get("DATACLOUD_AI_FACTORY_URL", "http://10.10.168.203:8569")
        self.ai_factory_token = os.environ.get("DATACLOUD_AI_FACTORY_TOKEN", "")
        self.loaded_agent_ids: list[str] = []
        repo_root = _datacloud_repo_root()
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
                'Set a JSON array such as ["10000587","10000582"].'
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"DATACLOUD_AI_FACTORY_AGENT_IDS must be valid JSON: {exc}") from exc
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

        # 🆕 收集 mounted_objects（OBJECT/VIEW 类型的 resource_code）
        mounted_objects = []
        for rel in rel_resource_list:
            snapshot = self._rel_resource_snapshot(rel)
            resource_biz_type = snapshot["resourceBizType"]
            resource_code = snapshot["resourceCode"]
            if resource_biz_type in {"OBJECT", "VIEW"} and resource_code:
                mounted_objects.append(resource_code)

        logger.info(
            "[InitPlugin] Agent loaded: agent_id=%s prompt_keys=%s tool_count=%d tool_names=%s mounted_objects=%s",
            agent_id,
            sorted(dynamic_prompts.keys()),
            len(tool_names),
            tool_names,
            mounted_objects,
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

        # 🆕 修改检查逻辑：如果有 mounted_objects，即使没有动态工具也不算错误
        if not tool_names and not mounted_objects:
            empty_tool_agent_ids.append(agent_id)
            logger.error(
                "[InitPlugin] Agent has no tools and no mounted_objects: agent_id=%s tool_count=0 reason_summary=%s",
                agent_id,
                reason_summary,
            )
            return False

        # 🆕 构建 tool_metadata：保存每个工具的原始配置信息
        tool_metadata = {}
        for rel in rel_resource_list:
            snapshot = self._rel_resource_snapshot(rel)
            resource_code = snapshot["resourceCode"]
            resource_biz_type = snapshot["resourceBizType"]

            # 根据 biz_type 确定工具名称
            if resource_biz_type in {"OBJECT", "VIEW"}:
                tool_key = f"{resource_code}_query"
                tool_metadata[tool_key] = {
                    "resource_code": resource_code,
                    "resource_biz_type": resource_biz_type,
                    "resource_type": snapshot["resourceType"],
                    "resource_name": snapshot["resourceName"],
                }

        logger.info(
            "[InitPlugin] Agent tool_metadata: agent_id=%s tool_metadata=%s",
            agent_id,
            tool_metadata,
        )

        # 🆕 将 mounted_objects 传递给 AgentConfig
        current_map[agent_id] = AgentConfig(
            agent_id=agent_id,
            tools=dynamic_tools,
            prompts=dynamic_prompts,
            skills={},
            on_conflict="overwrite",
            extra={
                "tool_metadata": tool_metadata,
                "mounted_objects": mounted_objects,  # 🆕 传递挂载对象列表
            },
        )
        self._save_offline_cache(agent_id, detail_data)
        return True

    @staticmethod
    def _compile_task_prompt(detail: dict[str, Any]) -> str:
        parts: list[str] = []
        parts.append(f"{detail.get('corePersonaDefinition', '')}")
        return "\n\n".join(parts)

    @staticmethod
    def _rel_resource_snapshot(rel: dict[str, Any]) -> dict[str, str]:
        return {
            "resourceBizType": str(rel.get("resourceBizType") or ""),
            "resourceType": str(rel.get("resourceType") or ""),
            "resourceCode": str(rel.get("resourceCode") or ""),
            "resourceName": str(rel.get("resourceName") or ""),
            "resourceDesc": str(rel.get("resourceDesc") or ""),
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
            reason_summary.append(
                f"tool_name_collision_overwritten_by_delegate:{','.join(collisions)}"
            )
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
            logger.warning(
                "[InitPlugin][ToolLoad][Ontology] agent_id=%s skip: sdk unavailable", agent_id
            )
            return tools, report

        for rel in rel_resource_list:
            snapshot = self._rel_resource_snapshot(rel)
            resource_biz_type = snapshot["resourceBizType"]

            # 🆕 跳过 OBJECT/VIEW 类型，使用通用 query_objects 工具
            if resource_biz_type in {"OBJECT", "VIEW"}:
                report["skipped"].append({
                    **snapshot,
                    "reason": "object_view_use_generic_query_objects_tool"
                })
                logger.info(
                    "[InitPlugin][ToolLoad][Ontology] agent_id=%s skip resource_code=%s: "
                    "OBJECT/VIEW use generic query_objects tool",
                    agent_id,
                    snapshot["resourceCode"]
                )
                continue

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
                    model=os.environ.get("DATACLOUD_LLM_MODEL", "Qwen/Qwen3-235B-A22B"),
                    base_url=os.environ.get("DATACLOUD_LLM_API_BASE"),
                    api_key=os.environ.get("DATACLOUD_LLM_API_KEY"),
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
        # 🔍 打印原始 rel 配置（用于诊断 mounted_objects 问题）
        logger.info("=" * 80)
        logger.info("INIT_PLUGIN: BUILDING ONTOLOGY RESOURCE TOOLS")
        logger.info("=" * 80)
        logger.info("INIT_PLUGIN: resource_code=%s", resource_code)
        logger.info("INIT_PLUGIN: resource_biz_type=%s", resource_biz_type)
        logger.info("INIT_PLUGIN: resource_type=%s", resource_type)
        logger.info("INIT_PLUGIN: rel keys=%s", list(rel.keys()))
        for k, v in rel.items():
            if isinstance(v, str) and len(v) < 200:
                logger.info("INIT_PLUGIN:   %s: %s", k, v)
            else:
                logger.info("INIT_PLUGIN:   %s: <%s>", k, type(v).__name__)
        logger.info("=" * 80)

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
            # 获取对象的完整描述（包含字段、关系等）
            object_description = obj.get_description()
            tools[tool_name] = self._build_query_tool(
                obj.query,
                tool_name=tool_name,
                tool_desc=f"{rel.get('resourceName', resource_code)} {rel.get('resourceDesc', '')}".strip(),
                object_description=object_description,
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
        # 获取视图的完整描述（包含字段等）
        view_description = view.get_description()
        return {
            tool_name: self._build_query_tool(
                view.query,
                tool_name=tool_name,
                tool_desc=f"{rel.get('resourceName', resource_code)} {rel.get('resourceDesc', '')}".strip(),
                object_description=view_description,
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
                from datacloud_analysis.tools.delegate import build_delegate_tool  # noqa: PLC0415

                resource_name = str(rel.get("resourceName") or resource_code)
                resource_desc = str(rel.get("resourceDesc") or "")
                tools[resource_code] = build_delegate_tool(
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
        object_description: str = "",
    ) -> Any:
        """Wrap query(question=...) into a dispatcher-compatible async callable."""

        async def _tool(**params: Any) -> Any:
            question = (
                params.get("question") or params.get("query") or params.get("description") or ""
            )
            knowledge_context = params.get("knowledge_context") or ""
            return await query_func(
                question=str(question),
                include_plan=True,
                knowledge_context=str(knowledge_context) if knowledge_context else None,
            )

        # 构建详细的工具描述，包含对象 Schema
        doc_parts = [f"Query tool: {tool_name}"]
        if tool_desc:
            doc_parts.append(tool_desc)
        if object_description:
            doc_parts.append("\n" + object_description)
        doc_parts.append(
            "\nParams: question/query/description (one of them), knowledge_context (optional)."
        )

        _tool.__doc__ = "\n".join(doc_parts)
        return _tool

    def _resolve_scene_path(self, rel: dict[str, Any]) -> str:
        """Resolve ontology scene path for local test mode."""

        repo_root = _datacloud_repo_root()
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

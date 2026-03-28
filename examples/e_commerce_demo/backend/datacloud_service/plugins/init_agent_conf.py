"""初始化 dataCloud agent config，并输出加载结果。"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from by_framework import AgentConfig, Plugin, PluginManifest

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
            # 1. 请求 /getResourceListByPage 列表
            async with httpx.AsyncClient(verify=False) as client:
                list_payload = {
                    "pageNum": 1,
                    "pageSize": 100,
                    "statusList": [2],
                    "resourceName": "亦庄产业大脑数字员工",
                    "ownershipType": 0,
                    "resourceTypeList": ["DIG_EMPLOYEE"],
                    "language": "zh-CN",
                }
                # 加入认证和基本请求头
                if not self.ai_factory_token:
                    raise ValueError("DATACLOUD_AI_FACTORY_TOKEN is not set.")
                headers = {
                    "Content-Type": "application/json",
                    "Beyond-Token": self.ai_factory_token,
                }
                res_list = await client.post(
                    f"{self.ai_factory_url}/aiFactoryServer/new/resource/getResourceListByPage",
                    json=list_payload,
                    headers=headers,
                )
                if res_list.status_code != 200 or res_list.json().get("code") != 0:
                    raise ValueError(f"Failed to fetch resources list: {res_list.text}")

                rows = res_list.json().get("data", {}).get("rows", [])
                logger.info("[InitPlugin] Resource rows fetched: %d", len(rows))

                # 遍历处理远端每个 Agent 数据
                for row in rows:
                    agent_id = str(row.get("resourceId"))

                    # 2. 通过 resourceId 请求 /findDetailsById 详情
                    res_detail = await client.post(
                        f"{self.ai_factory_url}/aiFactoryServer/digitalEmployeeController/findDetailsById",
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

                        # 4. 通过 OntologyLoader 解析关联实体动作，绑定为 Tools
                        dynamic_tools = self._build_tools_from_ontology(
                            detail_data.get("relResourceList", [])
                        )
                        tool_names = sorted(dynamic_tools.keys())

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
                        if not tool_names:
                            empty_tool_agent_ids.append(agent_id)
                            logger.error(
                                "[InitPlugin] Agent has no tools: agent_id=%s tool_count=0 tool_names=%s",
                                agent_id,
                                tool_names,
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

                    loader.load_from_path(scene_path)
                    loader.load_scene_from_path(scene_path)

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
                        csv_base_dir=os.environ.get("DATACLOUD_GATEWAY_WORKSPACE_DIR", str(Path("/tmp/datacloud").resolve())),
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
                                dynamic_tools[f"{resource_code}_query"] = self._build_query_tool(obj.query)

                    elif resource_biz_type == "VIEW":
                        view = loader.get_view(resource_code)
                        if view:
                            # 3：当作为 VIEW 挂载时，补充 view.query()
                            dynamic_tools[f"{resource_code}_query"] = self._build_query_tool(view.query)
                except Exception as e:
                    logger.warning("本体解析失败 rel=%s err=%s", rel, e)
        return dynamic_tools

    def _build_query_tool(self, query_func):
        """Wrap query(question=...) into a dispatcher-compatible async callable."""

        async def _tool(**params):
            question = (
                params.get("question")
                or params.get("query")
                or params.get("description")
                or ""
            )
            return await query_func(question=str(question), include_plan=True)

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
            / "import_package"
            / "ontology"
            / "e_commerce_scene_01_data_analysis_full.json"
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

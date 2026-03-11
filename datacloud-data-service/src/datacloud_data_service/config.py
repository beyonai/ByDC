"""服务配置，基于 pydantic-settings。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.0
    ontology_path: str = "resources/ontology/crm_demo/objects_registry.json"
    scene_path: str = "resources/ontology/crm_demo/scene_01_data_analysis.json"
    csv_base_dir: str = "./tmp"
    max_plan_retries: int = 2
    sql_execution_mode: str = "internal"
    trace_log_path: str = "logs/query_trace.log"  # 环境变量 DC_TRACE_LOG_PATH
    trace_enabled: bool = True  # 环境变量 DC_TRACE_ENABLED
    znt_server: str = ""  # 术语服务地址，环境变量 DC_ZNT_SERVER

    model_config = {"env_prefix": "DC_", "env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

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
    # 查询结果溢出：超过阈值时存 CSV 并提供下载，避免模型上下文超长
    query_result_csv_threshold: int = 50  # 超过此行数则存 CSV
    query_result_preview_rows: int = 5  # 返回给模型的前几行预览
    api_base_url: str = "http://127.0.0.1:8080"  # 用于拼接下载地址，如 https://example.com
    max_plan_retries: int = 2
    sql_execution_mode: str = "internal"
    trace_log_path: str = "logs/query_trace.log"  # 环境变量 DC_TRACE_LOG_PATH
    trace_enabled: bool = False  # 环境变量 DC_TRACE_ENABLED
    znt_server: str = ""  # 术语服务地址，环境变量 DC_ZNT_SERVER
    # CORS 允许的源，逗号分隔，如 "http://localhost:3000,http://127.0.0.1:3000"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = {"env_prefix": "DC_", "env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

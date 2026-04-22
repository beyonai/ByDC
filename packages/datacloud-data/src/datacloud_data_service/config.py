"""服务配置，基于 pydantic-settings。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


def _repo_root() -> Path:
    """定位仓库根目录（含 AGENTS.md 或 pyproject.toml）。相对路径均相对此目录解析。

    调试时若 cwd 为子目录（如 examples/.../backend），仍能与 .env 中以仓库为基准的路径一致。
    """
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "AGENTS.md").is_file():
            return parent
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


class Settings(BaseSettings):
    llm_api_base: str = Field(default="", validation_alias="DATACLOUD_LLM_API_BASE")
    llm_api_key: str = Field(default="", validation_alias="DATACLOUD_LLM_API_KEY")
    llm_model: str = Field(default="gpt-4o", validation_alias="DATACLOUD_LLM_MODEL")
    llm_temperature: float = Field(default=0.0, validation_alias="DATACLOUD_LLM_TEMPERATURE")
    ontology_path: str = Field(
        default="resources/ontology/crm_demo/objects_registry.json",
        validation_alias="DATACLOUD_ONTOLOGY_PATH",
    )
    csv_base_dir: str = Field(default="./tmp", validation_alias="DATACLOUD_CSV_BASE_DIR")
    result_file_storage_type: str = Field(
        default="local",
        validation_alias="DATACLOUD_RESULT_FILE_STORAGE_TYPE",
    )
    result_file_base_dir: str = Field(
        default="./tmp",
        validation_alias="DATACLOUD_RESULT_FILE_BASE_DIR",
    )
    # 查询结果溢出：超过阈值时存 CSV 并提供下载，避免模型上下文超长
    query_result_csv_threshold: int = Field(
        default=5,
        validation_alias="DATACLOUD_QUERY_RESULT_CSV_THRESHOLD",
    )
    api_base_url: str = Field(
        default="http://127.0.0.1:8080",
        validation_alias="DATACLOUD_API_BASE_URL",
    )
    max_plan_retries: int = Field(default=2, validation_alias="DATACLOUD_MAX_PLAN_RETRIES")
    sql_execution_mode: str = Field(
        default="internal",
        validation_alias="DATACLOUD_SQL_EXECUTION_MODE",
    )
    trace_log_path: str = Field(
        default="logs/query_trace.log",
        validation_alias="DATACLOUD_TRACE_LOG_PATH",
    )
    trace_enabled: bool = Field(default=False, validation_alias="DATACLOUD_TRACE_ENABLED")
    loader_mode: str = Field(default="watch", validation_alias="DATACLOUD_LOADER_MODE")
    loader_reload_debounce_ms: int = Field(
        default=500,
        validation_alias="DATACLOUD_LOADER_RELOAD_DEBOUNCE_MS",
    )
    # CORS 允许的源，逗号分隔，如 "http://localhost:3000,http://127.0.0.1:3000"
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        validation_alias="DATACLOUD_CORS_ORIGINS",
    )

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def _resolve_relative_paths(self) -> Settings:
        root = _repo_root()
        for name in ("ontology_path", "csv_base_dir", "result_file_base_dir", "trace_log_path"):
            raw = getattr(self, name)
            p = Path(raw).expanduser()
            if not p.is_absolute():
                setattr(self, name, str((root / p).resolve()))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

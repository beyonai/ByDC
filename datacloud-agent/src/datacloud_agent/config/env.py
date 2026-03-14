"""Environment-variable based settings for the DataCloud agent.

All settings use pydantic-settings so they are loaded from env vars
(and optionally from a .env file loaded by the caller).

Environment variable naming convention:  DATACLOUD_<GROUP>_<KEY>
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LocaleSettings(BaseSettings):
    """Locale / language settings for the agent.

    Environment variables (prefix: ``DATACLOUD_AGENT_``):
        LOCALE  — BCP-47 style locale code. Defaults to ``zh_CN``.
                  Supported values: zh_CN, en_US.
                  At runtime, gateway can override per-request via
                  create_agent(locale=...) rather than the env var.
    """

    model_config = SettingsConfigDict(
        env_prefix="DATACLOUD_AGENT_",
        extra="ignore",
    )

    locale: str = Field(
        default="zh_CN",
        description="Default agent locale (zh_CN | en_US | …)",
    )


class DataServiceSettings(BaseSettings):
    """Settings for the external data-query microservice.

    Environment variables (prefix: ``DATACLOUD_DATA_SERVICE_``):
        BASE_URL     — e.g. http://10.45.134.164:8080
        API_KEY      — Bearer token value (optional)
        TENANT_ID    — X-Tenant-Id header (optional)
        SYSTEM_CODE  — X-System-Code header (optional, e.g. "crm")
        QUERY_PATH   — API path, default /api/v1/query
        TIMEOUT      — HTTP timeout in seconds, default 60
    """

    model_config = SettingsConfigDict(
        env_prefix="DATACLOUD_DATA_SERVICE_",
        extra="ignore",
    )

    base_url: str = Field(..., description="Base URL of the data query service")
    api_key: str = Field(default="", description="Bearer token for Authorization header")
    tenant_id: str = Field(default="", description="Static X-Tenant-Id header value")
    system_code: str = Field(default="", description="Static X-System-Code header value")
    query_path: str = Field(default="/api/v1/query", description="API path for NL query endpoint")
    timeout: int = Field(default=180, description="HTTP request timeout in seconds")


class KnowledgeSettings(BaseSettings):
    """知识图谱查询配置。未配置时 search_knowledge 返回空。"""

    model_config = SettingsConfigDict(env_prefix="DATACLOUD_KNOWLEDGE_", extra="ignore")

    graph_files: str = Field(
        default="",
        description="逗号分隔的图谱 JSON 文件路径，如 path/to/base.json,path/to/crm.json",
    )
    default_hops: int = Field(
        default=4,
        description="默认查询跳数",
    )

    @property
    def graph_files_list(self) -> list[str]:
        if not self.graph_files.strip():
            return []
        return [p.strip() for p in self.graph_files.split(",") if p.strip()]

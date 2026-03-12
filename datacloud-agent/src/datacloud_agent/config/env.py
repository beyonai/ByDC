"""Environment-variable based settings for the DataCloud agent.

All settings use pydantic-settings so they are loaded from env vars
(and optionally from a .env file loaded by the caller).

Environment variable naming convention:  DATACLOUD_<GROUP>_<KEY>
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    timeout: int = Field(default=60, description="HTTP request timeout in seconds")

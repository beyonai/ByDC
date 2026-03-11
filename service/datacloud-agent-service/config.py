"""Service configuration module.

Defines OpenClaw service-specific configuration using Pydantic settings.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """OpenClaw service configuration settings.

    These settings control the behavior of the OpenClaw Gateway Service.
    """

    model_config = SettingsConfigDict(
        env_prefix="DATACLOUD_SERVICE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service metadata
    service_name: str = "openclaw-gateway-service"
    service_version: str = "0.1.0"

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    workers: int = 1

    # Gateway SDK settings (for datacloud-agent integration)
    gateway_api_url: str = "http://localhost:8080"
    gateway_timeout: int = 30
    gateway_max_retries: int = 3

    # LLM API settings
    openai_api_key: str | None = Field(default=None, description="OpenAI API Key")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", description="OpenAI API Base URL"
    )

    # Logging
    log_level: str = "INFO"

    # CORS settings
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])


# Global settings instance
settings = ServiceSettings()

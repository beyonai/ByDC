"""Service configuration module.

Defines service-specific configuration using Pydantic settings.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Service-specific configuration settings.

    These settings control the behavior of the datacloud-agent-service.
    """

    model_config = SettingsConfigDict(
        env_prefix="DATACLOUD_SERVICE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service metadata
    service_name: str = "datacloud-agent-service"
    service_version: str = "0.1.0"

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    workers: int = 1

    # Gateway SDK settings
    gateway_api_url: str = "http://localhost:8080"
    gateway_timeout: int = 30
    gateway_max_retries: int = 3

    # Logging
    log_level: str = "INFO"

    # CORS settings
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])


# Global settings instance
settings = ServiceSettings()

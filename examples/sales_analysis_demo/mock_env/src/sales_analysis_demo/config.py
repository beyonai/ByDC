"""sales-analysis-demo 配置，支持 .env 加载."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://localhost:5432/crm_demo",
        validation_alias="DATACLOUD_DB_URL",
    )
    notice_url: str | None = Field(default=None, validation_alias="DATACLOUD_NOTICE_URL")
    redis_url: str | None = Field(default=None, validation_alias="DATACLOUD_REDIS_URL")
    redis_host: str = Field(default="localhost", validation_alias="DATACLOUD_REDIS_HOST")
    redis_port: int = Field(default=6379, validation_alias="DATACLOUD_REDIS_PORT")
    redis_db: int = Field(default=0, validation_alias="DATACLOUD_REDIS_DB")
    redis_password: str | None = Field(
        default=None,
        validation_alias="DATACLOUD_REDIS_PASSWORD",
    )


settings = Settings()

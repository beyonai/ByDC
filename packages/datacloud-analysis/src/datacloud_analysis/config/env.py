"""Environment variable definitions for datacloud-analysis.

All external configuration is read from environment variables here and
*nowhere else*.  Other modules must import ``Settings`` (or a sub-group)
from this module instead of calling ``os.getenv`` directly.

Variable naming convention:
  DATACLOUD_<GROUP>_<KEY>

Groups
------
PG            PostgreSQL (LangGraph checkpoint store)
LLM           Shared LLM settings reused by all runtime roles
EMBEDDING     Embedding model  (memory/knowledge vector search)
"""

from __future__ import annotations

import os
from collections.abc import Callable

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from datacloud_analysis.config.db_url import (
    build_postgres_connection_uri,
    resolve_checkpoint_schema,
)

# ---------------------------------------------------------------------------
# Sub-groups (composable, testable in isolation)
# ---------------------------------------------------------------------------


def _load_optional[T](loader: Callable[[], T]) -> T | None:
    """Load optional config group; only swallow validation/missing-env failures."""
    try:
        return loader()
    except (ValidationError, ValueError):
        return None


class PGSettings(BaseSettings):
    """Checkpoint PostgreSQL connection resolved from DATACLOUD_DB_*."""

    model_config = SettingsConfigDict(extra="ignore")

    checkpoint_uri: str = Field(
        default_factory=build_postgres_connection_uri,
        description="PostgreSQL DSN derived from DATACLOUD_DB_URL / USER / PASSWORD.",
    )
    checkpoint_schema: str = Field(
        default_factory=resolve_checkpoint_schema,
        description="Schema inferred from DATACLOUD_DB_URL query params. Defaults to 'public'.",
    )

    @field_validator("checkpoint_uri")
    @classmethod
    def _validate_checkpoint_uri(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "Missing DATACLOUD DB env vars: "
                "DATACLOUD_DB_URL / DATACLOUD_DB_USER / DATACLOUD_DB_PASSWORD"
            )
        return value


class LLMGroupSettings(BaseSettings):
    """Shared LLM settings reused by each logical role."""

    api_base: str = Field(..., description="Base URL of the LLM API endpoint.")
    api_key: str = Field(..., description="API key / bearer token.")
    model: str = Field(..., description="Model identifier passed to the API.")
    temperature: float = Field(default=0.0, description="Sampling temperature.")

    @classmethod
    def for_role(cls, role: str) -> LLMGroupSettings:
        """Factory: load the shared LLM settings for a logical role.

        Args:
            role: One of ``quick``, ``coding``, ``reasoning``, ``multimodal``.
        """
        api_base = os.getenv("DATACLOUD_LLM_API_BASE", "").strip()
        api_key = os.getenv("DATACLOUD_LLM_API_KEY", "").strip()
        model = os.getenv("DATACLOUD_LLM_MODEL", "").strip()
        raw_temperature = os.getenv("DATACLOUD_LLM_TEMPERATURE", "0.0").strip()

        if not (api_base and api_key and model):
            raise ValueError(
                "Missing DATACLOUD LLM env vars: "
                "DATACLOUD_LLM_API_BASE / DATACLOUD_LLM_API_KEY / DATACLOUD_LLM_MODEL"
            )

        try:
            temperature = float(raw_temperature)
        except ValueError as exc:
            raise ValueError(f"Invalid temperature for role {role}: {raw_temperature}") from exc

        return cls(
            api_base=api_base,
            api_key=api_key,
            model=model,
            temperature=temperature,
        )


class EmbeddingSettings(BaseSettings):
    """Settings for the embedding (vector) model."""

    model_config = SettingsConfigDict(env_prefix="DATACLOUD_EMBEDDING_", extra="ignore")

    api_base: str = Field(..., description="Base URL of the embedding API endpoint.")
    api_key: str = Field(..., description="API key.")
    model: str = Field(..., description="Embedding model identifier.")


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

    # --- 数据库连接配置 ---
    db_host: str = Field(default="", description="知识库数据库主机")
    db_port: int = Field(default=5432, description="知识库数据库端口")
    db_user: str = Field(default="", description="知识库数据库用户名")
    db_password: str = Field(default="", description="知识库数据库密码")
    db_name: str = Field(default="", description="知识库数据库名称")
    db_schema: str = Field(default="public", description="知识库数据库 schema")
    db_type: str = Field(default="postgresql", description="知识库数据库类型")
    knowledge_schema: str = Field(default="", description="知识 schema 标识")

    @property
    def graph_files_list(self) -> list[str]:
        if not self.graph_files.strip():
            return []
        return [p.strip() for p in self.graph_files.split(",") if p.strip()]


# ---------------------------------------------------------------------------
# New Settings classes (P2)
# ---------------------------------------------------------------------------


class AgentSettings(BaseSettings):
    """Agent-level settings."""

    model_config = SettingsConfigDict(env_prefix="DATACLOUD_AGENT_", extra="ignore")

    locale: str = Field(default="zh_CN", description="Agent locale, e.g. zh_CN or en_US")


class GatewaySettings(BaseSettings):
    """Gateway / worker layer settings (Redis + worker_id)."""

    model_config = SettingsConfigDict(env_prefix="DATACLOUD_GATEWAY_", extra="ignore")

    redis_host: str = Field(default="", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_username: str = Field(default="", description="Redis username")
    redis_password: str = Field(default="", description="Redis password")
    redis_db: int = Field(default=0, description="Redis database index")
    worker_id: str = Field(default="", description="Worker node identifier")


class ExecutionSettings(BaseSettings):
    """Execution / ReAct loop settings."""

    model_config = SettingsConfigDict(env_prefix="DATACLOUD_", extra="ignore")

    react_max_rounds: int = Field(default=10, description="Maximum ReAct loop rounds")


# ---------------------------------------------------------------------------
# Aggregate Settings — single object for the whole SDK
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Aggregate all environment variables for the SDK.

    Raises ``ValidationError`` on startup if any required variable is missing
    (fail-fast principle).

    Usage::

        from datacloud_analysis.config.env import Settings
        cfg = Settings()
        print(cfg.pg.checkpoint_uri)
        llm_quick = cfg.llm_quick
    """

    model_config = SettingsConfigDict(extra="ignore")

    # --- sub-groups loaded lazily via validators ---
    pg: PGSettings = Field(default_factory=PGSettings)

    # LLM roles
    llm_quick: LLMGroupSettings | None = Field(default=None)
    llm_coding: LLMGroupSettings | None = Field(default=None)
    llm_reasoning: LLMGroupSettings | None = Field(default=None)
    llm_multimodal: LLMGroupSettings | None = Field(default=None)

    embedding: EmbeddingSettings | None = Field(default=None)
    knowledge: KnowledgeSettings | None = Field(default=None)

    # New settings groups (P2)
    agent: AgentSettings | None = Field(default=None)
    gateway: GatewaySettings | None = Field(default=None)
    execution: ExecutionSettings | None = Field(default=None)

    @model_validator(mode="after")
    def _load_llm_roles(self) -> Settings:
        """Populate LLM role settings from their env prefixes (soft-fail when missing)."""
        roles = {
            "llm_quick": "quick",
            "llm_coding": "coding",
            "llm_reasoning": "reasoning",
            "llm_multimodal": "multimodal",
        }
        for attr, role in roles.items():
            try:
                role_config = LLMGroupSettings.for_role(role)
            except (ValidationError, ValueError):
                role_config = None
            object.__setattr__(self, attr, role_config)

        object.__setattr__(
            self, "embedding", _load_optional(lambda: EmbeddingSettings.model_validate({}))
        )
        object.__setattr__(
            self, "knowledge", _load_optional(lambda: KnowledgeSettings.model_validate({}))
        )
        object.__setattr__(self, "agent", _load_optional(lambda: AgentSettings.model_validate({})))
        object.__setattr__(
            self, "gateway", _load_optional(lambda: GatewaySettings.model_validate({}))
        )
        object.__setattr__(
            self, "execution", _load_optional(lambda: ExecutionSettings.model_validate({}))
        )

        return self

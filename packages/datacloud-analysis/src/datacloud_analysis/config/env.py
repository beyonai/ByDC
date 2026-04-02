"""Environment variable definitions for datacloud-analysis.

All external configuration is read from environment variables here and
*nowhere else*.  Other modules must import ``Settings`` (or a sub-group)
from this module instead of calling ``os.getenv`` directly.

Variable naming convention:
  DATACLOUD_<GROUP>_<KEY>

Groups
------
PG            PostgreSQL (LangGraph checkpoint store)
WORKSPACE     File-system paths for public/private/task directories
DATA_SERVICE  External data-query microservice (HTTP API)
LLM_QUICK     Fast Q&A model  (intent classification, routing)
LLM_CODING    Code generation model  (script writing, sbx_run_code)
LLM_REASONING Deep reasoning model  (planning, summarisation)
LLM_MULTIMODAL Multi-modal model  (image/table understanding)
EMBEDDING     Embedding model  (memory/knowledge vector search)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Sub-groups (composable, testable in isolation)
# ---------------------------------------------------------------------------

class PGSettings(BaseSettings):
    """PostgreSQL connection used by LangGraph AsyncPostgresSaver & PostgresStore."""

    model_config = SettingsConfigDict(env_prefix="DATACLOUD_PG_", extra="ignore")

    checkpoint_uri: str = Field(
        ...,
        description="Full PostgreSQL DSN, e.g. postgresql://user:pass@host:5432/db?sslmode=disable",
    )
    checkpoint_schema: str = Field(
        default="public",
        description="Schema that holds checkpoint tables. Defaults to 'public'.",
    )


class WorkspaceSettings(BaseSettings):
    """File-system root directories for the workspace (design §4.2)."""

    model_config = SettingsConfigDict(env_prefix="DATACLOUD_WORKSPACE_", extra="ignore")

    public_root: Path = Field(
        ...,
        description="Enterprise public domain root (maps to public/datacloud/ in design).",
    )
    private_root: Path = Field(
        ...,
        description=(
            "User private domain root prefix. "
            "Actual per-user path is built at runtime: {private_root}/{user_id}/…"
        ),
    )
    tasks_root: Path | None = Field(
        default=None,
        description=(
            "Optional separate root for task sandboxes. "
            "Falls back to {private_root}/{user_id}/workspaces/tasks when unset."
        ),
    )


class LLMGroupSettings(BaseSettings):
    """Settings for one LLM role (quick / coding / reasoning / multimodal).

    Instantiate with a role-specific env_prefix, e.g.:
        LLMGroupSettings(_env_prefix="DATACLOUD_LLM_QUICK_")
    """

    api_base: str = Field(..., description="Base URL of the LLM API endpoint.")
    api_key: str = Field(..., description="API key / bearer token.")
    model: str = Field(..., description="Model identifier passed to the API.")
    temperature: float = Field(default=0.0, description="Sampling temperature.")

    @classmethod
    def for_role(cls, role: str) -> "LLMGroupSettings":
        """Factory: load settings for the given role from its env prefix.

        Args:
            role: One of ``quick``, ``coding``, ``reasoning``, ``multimodal``.
        """
        prefix = f"DATACLOUD_LLM_{role.upper()}_"
        return cls(_env_prefix=prefix)  # type: ignore[call-arg]


class DataServiceSettings(BaseSettings):
    """HTTP client settings for the external data-query microservice.

    The data service is used by dynamic query tools mounted into each agent.
    Static header defaults are configured here; per-request runtime context
    (if any) should be injected by the caller.
    """

    model_config = SettingsConfigDict(env_prefix="DATACLOUD_DATA_SERVICE_", extra="ignore")

    base_url: str = Field(
        ...,
        description="Base URL of the data query service, e.g. http://10.45.134.164:8080",
    )
    api_key: str = Field(
        default="",
        description="Bearer token for Authorization header.",
    )
    tenant_id: str = Field(
        default="",
        description="Static X-Tenant-Id header value.",
    )
    system_code: str = Field(
        default="",
        description="Static X-System-Code header value (e.g. 'crm').",
    )
    query_path: str = Field(
        default="/api/v1/query",
        description="API path for the NL query endpoint.",
    )
    timeout: int = Field(
        default=180,
        description="HTTP request timeout in seconds.",
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
    knowledge_schema: str = Field(
        default="",
        validation_alias="DATACLOUD_KNOWLEDGE_SCHEMA",
        description="知识 schema 标识（裸变量，无前缀）",
    )

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


class AIFactorySettings(BaseSettings):
    """AI Factory settings (token + agent_ids list)."""

    model_config = SettingsConfigDict(env_prefix="DATACLOUD_AI_FACTORY_", extra="ignore")

    token: str = Field(default="", description="AI Factory API token")
    agent_ids: list[str] = Field(default_factory=list, description="AI Factory agent IDs (JSON array)")

    @field_validator("agent_ids", mode="before")
    @classmethod
    def _parse_agent_ids(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
                return [str(parsed)]
            except (json.JSONDecodeError, ValueError):
                # Treat as comma-separated fallback
                return [item.strip() for item in v.split(",") if item.strip()]
        return v


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
        print(cfg.workspace.public_root)
        llm_quick = cfg.llm_quick
    """

    model_config = SettingsConfigDict(extra="ignore")

    # --- sub-groups loaded lazily via validators ---
    pg: PGSettings = Field(default_factory=PGSettings)
    workspace: WorkspaceSettings = Field(default_factory=WorkspaceSettings)
    data_service: DataServiceSettings = Field(default_factory=DataServiceSettings)

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
    ai_factory: AIFactorySettings | None = Field(default=None)
    execution: ExecutionSettings | None = Field(default=None)

    @model_validator(mode="after")
    def _load_llm_roles(self) -> "Settings":
        """Populate LLM role settings from their env prefixes (soft-fail when missing)."""
        roles = {
            "llm_quick": "quick",
            "llm_coding": "coding",
            "llm_reasoning": "reasoning",
            "llm_multimodal": "multimodal",
        }
        for attr, role in roles.items():
            try:
                object.__setattr__(self, attr, LLMGroupSettings.for_role(role))
            except Exception:  # noqa: BLE001
                pass  # Role not configured; callers must check for None

        try:
            object.__setattr__(self, "embedding", EmbeddingSettings())
        except Exception:  # noqa: BLE001
            pass

        try:
            object.__setattr__(self, "knowledge", KnowledgeSettings())
        except Exception:  # noqa: BLE001
            pass

        try:
            object.__setattr__(self, "agent", AgentSettings())
        except Exception:  # noqa: BLE001
            pass

        try:
            object.__setattr__(self, "gateway", GatewaySettings())
        except Exception:  # noqa: BLE001
            pass

        try:
            object.__setattr__(self, "ai_factory", AIFactorySettings())
        except Exception:  # noqa: BLE001
            pass

        try:
            object.__setattr__(self, "execution", ExecutionSettings())
        except Exception:  # noqa: BLE001
            pass

        return self

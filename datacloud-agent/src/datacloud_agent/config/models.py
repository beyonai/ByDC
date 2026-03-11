"""Pydantic models for OpenClaw Gateway configuration."""

from pydantic import BaseModel, Field


class MessagesConfig(BaseModel):
    """Message handling configuration."""

    max_message_length: int = Field(
        default=1048576, ge=1, description="Maximum message length in bytes"
    )
    default_queue_mode: str = Field(
        default="async", description="Default queue mode: 'async' or 'sync'"
    )


class InboundConfig(BaseModel):
    """Inbound message configuration."""

    debounce_ms: int = Field(default=100, ge=0, description="Debounce time in milliseconds")
    dedupe_window_ms: int = Field(
        default=500, ge=0, description="Deduplication window in milliseconds"
    )


class QueueConfig(BaseModel):
    """Queue settings configuration."""

    default_mode: str = Field(default="async", description="Default queue mode: 'async' or 'sync'")
    max_queue_size: int = Field(default=1000, ge=1, description="Maximum queue size")
    drop_policy: str = Field(
        default="reject", description="Drop policy: 'reject', 'drop_oldest', 'drop_newest'"
    )


class AgentConfig(BaseModel):
    """Agent configuration."""

    default_agent: str = Field(default="main", description="Default agent name")
    available_agents: dict[str, str] = Field(
        default_factory=dict, description="Mapping of agent names to agent types"
    )


class GatewayConfig(BaseModel):
    """Main OpenClaw Gateway configuration."""

    port: int = Field(default=8080, ge=1, le=65535, description="Gateway port")
    host: str = Field(default="127.0.0.1", description="Gateway host address")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    messages: MessagesConfig = Field(
        default_factory=MessagesConfig, description="Message handling config"
    )
    inbound: InboundConfig = Field(
        default_factory=InboundConfig, description="Inbound message config"
    )
    queue: QueueConfig = Field(default_factory=QueueConfig, description="Queue settings")
    agent: AgentConfig = Field(default_factory=AgentConfig, description="Agent configuration")

"""Types for the four-layer prompt system."""

from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class LayerType(str, Enum):
    """Four-layer architecture for system prompts."""

    IDENTITY = "identity"
    OPERATION = "operation"
    KNOWLEDGE = "knowledge"
    COLLABORATION = "collaboration"


class PromptConfig(BaseModel):
    """Configuration for a single prompt file.

    Attributes:
        path: Path to the prompt file (relative to prompts directory).
        layer: Layer type assigned to this file.
        priority: Optional priority within the layer (lower = earlier).
    """

    path: Path
    layer: LayerType
    priority: Optional[int] = Field(default=None, ge=0)


class SystemPromptConfig(BaseModel):
    """Configuration for the system prompt builder.

    Attributes:
        prompts_dir: Directory containing prompt files (default: "prompts").
        bootstrap_max_chars: Maximum characters for bootstrap (default: 100_000).
        head_tail_ratio: Ratio of head vs tail when truncating (default: 0.7).
        layer_order: Order of layers in final prompt (default: IDENTITY, OPERATION, KNOWLEDGE, COLLABORATION).
        default_layer: Default layer for unrecognized .md files (default: OPERATION).
        file_layer_mapping: Mapping from file names to layer types.
    """

    prompts_dir: Path = Field(default=Path("prompts"))
    bootstrap_max_chars: int = Field(default=100_000, ge=1)
    head_tail_ratio: float = Field(default=0.7, ge=0.0, le=1.0)
    layer_order: list[LayerType] = Field(
        default_factory=lambda: [
            LayerType.IDENTITY,
            LayerType.OPERATION,
            LayerType.KNOWLEDGE,
            LayerType.COLLABORATION,
        ]
    )
    default_layer: LayerType = Field(default=LayerType.OPERATION)
    file_layer_mapping: Dict[str, LayerType] = Field(
        default_factory=lambda: {
            "SOUL.md": LayerType.IDENTITY,
            "IDENTITY.md": LayerType.IDENTITY,
            "USER.md": LayerType.IDENTITY,
            "AGENTS.md": LayerType.COLLABORATION,
        }
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

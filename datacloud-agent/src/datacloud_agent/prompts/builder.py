"""System prompt builder for the four‑layer architecture."""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List

from .loader import PromptLoader
from .types import LayerType, SystemPromptConfig

logger = logging.getLogger(__name__)


class SystemPromptBuilder:
    """Builds a system prompt from the four‑layer prompt files.

    Args:
        config: Configuration for the builder.
    """

    def __init__(self, config: SystemPromptConfig) -> None:
        self.config = config
        self.loader = PromptLoader(config)

    async def build(self) -> str:
        """Build the system prompt.

        Returns:
            The assembled system prompt string.
        """
        # Load files grouped by layer
        grouped = await self.loader.load_all()

        # Concatenate contents in layer order
        layers_content = []
        for layer in self.config.layer_order:
            files = grouped.get(layer, [])
            if not files:
                logger.debug("No files found for layer %s", layer)
                continue
            for file_path, content in files:
                layers_content.append(content)

        full_prompt = "\n\n".join(layers_content)

        # Apply global truncation if needed
        if len(full_prompt) > self.config.bootstrap_max_chars:
            full_prompt = self._truncate_global(
                full_prompt,
                self.config.bootstrap_max_chars,
                self.config.head_tail_ratio,
            )

        return full_prompt

    @staticmethod
    def _truncate_global(content: str, max_chars: int, head_tail_ratio: float) -> str:
        """Truncate the entire prompt preserving head and tail.

        Args:
            content: Full concatenated prompt.
            max_chars: Maximum allowed characters.
            head_tail_ratio: Ratio of head vs tail (0.0 = all tail, 1.0 = all head).

        Returns:
            Truncated prompt.
        """
        head_chars = int(max_chars * head_tail_ratio)
        tail_chars = max_chars - head_chars

        head = content[:head_chars]
        tail = content[-tail_chars:] if tail_chars > 0 else ""

        # Insert ellipsis to indicate omitted middle part
        return f"{head}\n\n[...]\n\n{tail}"

    async def build_with_metadata(self) -> Dict[str, Any]:
        """Build the system prompt and return metadata.

        Returns:
            Dictionary with keys:
                - "prompt": the assembled system prompt
                - "layer_stats": summary of characters per layer
                - "file_stats": summary of files loaded
        """
        grouped = await self.loader.load_all()

        layer_stats = {}
        file_stats = []
        layers_content = []

        for layer in self.config.layer_order:
            files = grouped.get(layer, [])
            layer_chars = 0
            for file_path, content in files:
                file_chars = len(content)
                layer_chars += file_chars
                file_stats.append(
                    {
                        "file": str(file_path),
                        "layer": layer.value,
                        "chars": file_chars,
                    }
                )
                layers_content.append(content)
            layer_stats[layer.value] = layer_chars

        full_prompt = "\n\n".join(layers_content)

        if len(full_prompt) > self.config.bootstrap_max_chars:
            full_prompt = self._truncate_global(
                full_prompt,
                self.config.bootstrap_max_chars,
                self.config.head_tail_ratio,
            )

        return {
            "prompt": full_prompt,
            "layer_stats": layer_stats,
            "file_stats": file_stats,
        }

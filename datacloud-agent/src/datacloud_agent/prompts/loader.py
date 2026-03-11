"""Loader for four-layer prompt files."""

import asyncio
import logging
from pathlib import Path

from .types import LayerType, SystemPromptConfig

logger = logging.getLogger(__name__)


class PromptLoader:
    """Loads prompt files from a directory and organizes them by layer.

    Args:
        config: Configuration for the loader.
    """

    def __init__(self, config: SystemPromptConfig) -> None:
        self.config = config
        self._prompts_dir = config.prompts_dir.resolve()

    async def load_all(self) -> dict[LayerType, list[tuple[Path, str]]]:
        """Load all .md files from the prompts directory.

        Returns:
            Mapping from layer type to list of (file_path, content) tuples.
        """
        if not await asyncio.to_thread(self._prompts_dir.exists):
            logger.warning("Prompts directory does not exist: %s", self._prompts_dir)
            return {layer: [] for layer in LayerType}

        # Gather all .md files
        md_files = []
        for file_path in await asyncio.to_thread(self._collect_md_files):
            layer = self._determine_layer(file_path)
            md_files.append((file_path, layer))

        # Load contents in parallel
        tasks = [self._load_file_content(file_path, layer) for file_path, layer in md_files]
        loaded = await asyncio.gather(*tasks)

        # Group by layer
        grouped: dict[LayerType, list[tuple[Path, str]]] = {layer: [] for layer in LayerType}
        for (file_path, layer), content in zip(md_files, loaded, strict=False):
            if content:
                grouped[layer].append((file_path, content))

        # Sort each group by file name (or could be by priority later)
        for layer in grouped:
            grouped[layer].sort(key=lambda x: x[0].name)

        return grouped

    def _collect_md_files(self) -> list[Path]:
        """Synchronous helper to collect all .md files recursively."""
        files = []
        for path in self._prompts_dir.rglob("*.md"):
            if path.is_file():
                files.append(path)
        return files

    def _determine_layer(self, file_path: Path) -> LayerType:
        """Determine the layer for a given file path."""
        try:
            rel_path: Path | str = file_path.relative_to(self._prompts_dir)
        except ValueError:
            # File is outside prompts_dir (should not happen with rglob)
            rel_path = file_path.name
        # Check mapping by file name (relative to prompts_dir)
        for pattern, layer in self.config.file_layer_mapping.items():
            if str(rel_path) == pattern or file_path.name == pattern:
                return layer
        # Default layer
        return self.config.default_layer

    async def _load_file_content(self, file_path: Path, _layer: LayerType) -> str | None:
        """Load and optionally truncate file content."""
        try:
            content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        except Exception as e:
            logger.error("Failed to read %s: %s", file_path, e)
            return None

        # Apply truncation if content exceeds per‑file limit?
        # For now, we rely on builder‑level truncation.
        return content

    @staticmethod
    def truncate_content(content: str, max_chars: int, head_tail_ratio: float) -> str:
        """Truncate content preserving head and tail portions.

        Args:
            content: Original content.
            max_chars: Maximum allowed characters.
            head_tail_ratio: Ratio of head vs tail (0.0 = all tail, 1.0 = all head).

        Returns:
            Truncated content.
        """
        if len(content) <= max_chars:
            return content

        head_chars = int(max_chars * head_tail_ratio)
        tail_chars = max_chars - head_chars

        head = content[:head_chars]
        tail = content[-tail_chars:] if tail_chars > 0 else ""

        # Ensure we don't cut in the middle of a line (optional)
        # Simple approach: join with ellipsis
        return f"{head}\n\n[...]\n\n{tail}"

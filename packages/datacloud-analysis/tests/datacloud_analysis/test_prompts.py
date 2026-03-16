"""Tests for the four-layer prompt system."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from datacloud_analysis.prompts import (
    LayerType,
    PromptConfig,
    PromptLoader,
    SystemPromptBuilder,
    SystemPromptConfig,
)


@pytest.fixture
def temp_prompts_dir():
    """Create a temporary directory with sample prompt files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dir_path = Path(tmpdir)
        # Create layer files
        (dir_path / "SOUL.md").write_text("# SOUL\n\nCore identity.")
        (dir_path / "IDENTITY.md").write_text("# IDENTITY\n\nAgent identity.")
        (dir_path / "USER.md").write_text("# USER\n\nUser persona.")
        (dir_path / "AGENTS.md").write_text("# AGENTS\n\nCollaboration rules.")
        # Create additional .md files for other layers
        (dir_path / "operations.md").write_text("# Operations\n\nOperational instructions.")
        (dir_path / "knowledge.md").write_text("# Knowledge\n\nKnowledge base content.")
        # Create a subdirectory with nested .md file
        sub = dir_path / "sub"
        sub.mkdir()
        (sub / "nested.md").write_text("# Nested\n\nNested content.")
        yield dir_path


class TestLayerType:
    """Tests for LayerType enum."""

    def test_values(self):
        """Test enum values."""
        assert LayerType.IDENTITY.value == "identity"
        assert LayerType.OPERATION.value == "operation"
        assert LayerType.KNOWLEDGE.value == "knowledge"
        assert LayerType.COLLABORATION.value == "collaboration"


class TestSystemPromptConfig:
    """Tests for SystemPromptConfig."""

    def test_defaults(self):
        """Test default configuration."""
        config = SystemPromptConfig()
        assert config.prompts_dir == Path("prompts")
        assert config.bootstrap_max_chars == 100_000
        assert config.head_tail_ratio == 0.7
        assert config.layer_order == [
            LayerType.IDENTITY,
            LayerType.OPERATION,
            LayerType.KNOWLEDGE,
            LayerType.COLLABORATION,
        ]
        assert config.default_layer == LayerType.OPERATION
        assert config.file_layer_mapping == {
            "SOUL.md": LayerType.IDENTITY,
            "IDENTITY.md": LayerType.IDENTITY,
            "USER.md": LayerType.IDENTITY,
            "AGENTS.md": LayerType.COLLABORATION,
        }

    def test_custom_prompts_dir(self):
        """Test custom prompts directory."""
        config = SystemPromptConfig(prompts_dir=Path("/custom/prompts"))
        assert config.prompts_dir == Path("/custom/prompts")

    def test_custom_bootstrap_max_chars(self):
        """Test custom bootstrap max characters."""
        config = SystemPromptConfig(bootstrap_max_chars=5000)
        assert config.bootstrap_max_chars == 5000

    def test_custom_head_tail_ratio(self):
        """Test custom head-tail ratio."""
        config = SystemPromptConfig(head_tail_ratio=0.5)
        assert config.head_tail_ratio == 0.5

    def test_custom_layer_order(self):
        """Test custom layer order."""
        config = SystemPromptConfig(layer_order=[LayerType.COLLABORATION, LayerType.IDENTITY])
        assert config.layer_order == [LayerType.COLLABORATION, LayerType.IDENTITY]

    def test_custom_default_layer(self):
        """Test custom default layer."""
        config = SystemPromptConfig(default_layer=LayerType.KNOWLEDGE)
        assert config.default_layer == LayerType.KNOWLEDGE

    def test_custom_file_layer_mapping(self):
        """Test custom file layer mapping."""
        mapping = {"CUSTOM.md": LayerType.KNOWLEDGE}
        config = SystemPromptConfig(file_layer_mapping=mapping)
        assert config.file_layer_mapping == mapping


class TestPromptLoader:
    """Tests for PromptLoader."""

    @pytest.mark.asyncio
    async def test_load_all(self, temp_prompts_dir):
        """Test loading all .md files."""
        config = SystemPromptConfig(prompts_dir=temp_prompts_dir)
        loader = PromptLoader(config)
        grouped = await loader.load_all()

        # Check that all expected files are present
        assert LayerType.IDENTITY in grouped
        assert LayerType.OPERATION in grouped
        assert LayerType.KNOWLEDGE in grouped
        assert LayerType.COLLABORATION in grouped

        # Identity layer should have 3 files
        identity_files = grouped[LayerType.IDENTITY]
        assert len(identity_files) == 3
        filenames = {path.name for path, _ in identity_files}
        assert filenames == {"SOUL.md", "IDENTITY.md", "USER.md"}

        # Collaboration layer should have AGENTS.md
        collab_files = grouped[LayerType.COLLABORATION]
        assert len(collab_files) == 1
        assert collab_files[0][0].name == "AGENTS.md"

        # Operation layer (default) should have operations.md, knowledge.md, nested.md
        operation_files = grouped[LayerType.OPERATION]
        assert len(operation_files) == 3
        filenames = {path.name for path, _ in operation_files}
        assert filenames == {"operations.md", "knowledge.md", "nested.md"}

        # Knowledge layer should be empty (no mapping for knowledge.md)
        knowledge_files = grouped[LayerType.KNOWLEDGE]
        assert len(knowledge_files) == 0

    @pytest.mark.asyncio
    async def test_load_all_empty_directory(self):
        """Test loading from empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SystemPromptConfig(prompts_dir=Path(tmpdir))
            loader = PromptLoader(config)
            grouped = await loader.load_all()
            for layer in LayerType:
                assert grouped[layer] == []

    @pytest.mark.asyncio
    async def test_load_all_nonexistent_directory(self):
        """Test loading from non‑existent directory."""
        config = SystemPromptConfig(prompts_dir=Path("/nonexistent/path"))
        loader = PromptLoader(config)
        grouped = await loader.load_all()
        for layer in LayerType:
            assert grouped[layer] == []

    @pytest.mark.asyncio
    async def test_truncate_content(self):
        """Test content truncation."""
        content = "A" * 200
        truncated = PromptLoader.truncate_content(content, max_chars=100, head_tail_ratio=0.6)
        # Expected: head = 60 chars, tail = 40 chars
        assert len(truncated) <= 100 + len("\n\n[...]\n\n")
        assert truncated.startswith("A" * 60)
        assert truncated.endswith("A" * 40)
        assert "[...]" in truncated

    @pytest.mark.asyncio
    async def test_truncate_content_no_truncation(self):
        """Test truncation when content is within limit."""
        content = "Short content"
        truncated = PromptLoader.truncate_content(content, max_chars=100, head_tail_ratio=0.7)
        assert truncated == content


class TestSystemPromptBuilder:
    """Tests for SystemPromptBuilder."""

    @pytest.mark.asyncio
    async def test_build(self, temp_prompts_dir):
        """Test building a system prompt."""
        config = SystemPromptConfig(prompts_dir=temp_prompts_dir)
        builder = SystemPromptBuilder(config)
        prompt = await builder.build()

        # Prompt should contain all files concatenated in layer order
        assert "# SOUL" in prompt
        assert "# IDENTITY" in prompt
        assert "# USER" in prompt
        assert "# AGENTS" in prompt
        assert "# Operations" in prompt
        assert "# Knowledge" in prompt
        assert "# Nested" in prompt

        # Check layer ordering: IDENTITY files first
        # Since we have three identity files, they should appear before operation files
        # We'll just verify that SOUL appears before operations (since identity first)
        soul_pos = prompt.find("# SOUL")
        ops_pos = prompt.find("# Operations")
        assert soul_pos < ops_pos

    @pytest.mark.asyncio
    async def test_build_with_truncation(self, temp_prompts_dir):
        """Test building with global truncation."""
        # Create a large content to exceed bootstrap limit
        large_content = "X" * 5000
        (temp_prompts_dir / "large.md").write_text(large_content)

        config = SystemPromptConfig(prompts_dir=temp_prompts_dir, bootstrap_max_chars=1000)
        builder = SystemPromptBuilder(config)
        prompt = await builder.build()

        # Prompt length should be <= 1000 + overhead for ellipsis
        assert len(prompt) <= 1000 + len("\n\n[...]\n\n")
        # Should contain truncation indicator
        assert "[...]" in prompt

    @pytest.mark.asyncio
    async def test_build_with_metadata(self, temp_prompts_dir):
        """Test building with metadata."""
        config = SystemPromptConfig(prompts_dir=temp_prompts_dir)
        builder = SystemPromptBuilder(config)
        result = await builder.build_with_metadata()

        assert "prompt" in result
        assert "layer_stats" in result
        assert "file_stats" in result

        # Check layer stats
        stats = result["layer_stats"]
        assert isinstance(stats, dict)
        # Should have entries for each layer present
        assert "identity" in stats
        assert "collaboration" in stats
        assert "operation" in stats
        assert "knowledge" in stats

        # Check file stats
        file_stats = result["file_stats"]
        assert isinstance(file_stats, list)
        assert len(file_stats) >= 7  # all .md files

    @pytest.mark.asyncio
    async def test_build_empty_directory(self):
        """Test building from empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SystemPromptConfig(prompts_dir=Path(tmpdir))
            builder = SystemPromptBuilder(config)
            prompt = await builder.build()
            assert prompt == ""

"""Tests for backend preset registration and name resolution (§6.2 of architecture doc)."""

from __future__ import annotations

import pytest

from datacloud_platform.backends.presets import _PRESETS, register_preset
from datacloud_platform.backends.registry import (
    _BACKEND_DEFAULTS,
    register_backend_type,
    register_implementation,
)
from datacloud_platform.backends.resolution import resolve_backend_names


def _setup_dimensions() -> None:
    """Register the standard 4 Backend dimensions with known defaults."""
    register_backend_type("ontology", "datacloud-data")
    register_backend_type("term", "datacloud-knowledge")
    register_backend_type("execution", "datacloud-server")
    register_backend_type("storage", "datacloud-data")

    # Register minimal implementations so get_backend_factory works
    register_implementation("ontology", "datacloud-data", lambda: None)  # type: ignore[arg-type,return-value]
    register_implementation("term", "datacloud-knowledge", lambda: None)  # type: ignore[arg-type,return-value]
    register_implementation("execution", "datacloud-server", lambda: None)  # type: ignore[arg-type,return-value]
    register_implementation("storage", "datacloud-data", lambda: None)  # type: ignore[arg-type,return-value]
    register_implementation("ontology", "remote-http", lambda: None)  # type: ignore[arg-type,return-value]
    register_implementation("term", "remote-http", lambda: None)  # type: ignore[arg-type,return-value]
    register_implementation("execution", "none", lambda: None)  # type: ignore[arg-type,return-value]
    register_implementation("storage", "none", lambda: None)  # type: ignore[arg-type,return-value]


class TestRegisterPreset:
    """Tests for register_preset()."""

    def test_normal_registration(self) -> None:
        """register_preset stores overrides in _PRESETS."""
        _setup_dimensions()
        register_preset("TEST", {"ontology": "remote-http"})
        assert "TEST" in _PRESETS
        assert _PRESETS["TEST"] == {"ontology": "remote-http"}

    def test_empty_preset(self) -> None:
        """Empty overrides dict is valid — means all defaults."""
        _setup_dimensions()
        register_preset("EMPTY", {})
        assert _PRESETS["EMPTY"] == {}

    def test_unknown_dimension_raises_valueerror(self) -> None:
        """A preset key that is not a registered dimension raises ValueError
        when resolved via resolve_backend_names."""
        _setup_dimensions()
        register_preset("BAD", {"cache": "memory"})
        with pytest.raises(ValueError, match="Unknown backend type"):
            resolve_backend_names("BAD", {})


class TestResolveBackendNames:
    """Tests for resolve_backend_names() — the 3-layer resolution function."""

    def test_empty_source_type_all_defaults(self) -> None:
        """Empty source_type skips the preset layer → all defaults."""
        _setup_dimensions()
        result = resolve_backend_names("", {})
        assert result == _BACKEND_DEFAULTS

    def test_local_preset_all_defaults(self) -> None:
        """LOCAL with empty overrides → all defaults."""
        _setup_dimensions()
        register_preset("LOCAL", {})
        result = resolve_backend_names("LOCAL", {})
        assert result == _BACKEND_DEFAULTS

    def test_remote_preset_overrides(self) -> None:
        """REMOTE preset overrides ontology→remote-http, knowledge→remote-http,
        execution→none, storage→none."""
        _setup_dimensions()
        register_preset(
            "REMOTE",
            {
                "ontology": "remote-http",
                "term": "remote-http",
                "execution": "none",
                "storage": "none",
            },
        )
        result = resolve_backend_names("REMOTE", {})
        assert result["ontology"] == "remote-http"
        assert result["term"] == "remote-http"
        assert result["execution"] == "none"
        assert result["storage"] == "none"

    def test_preset_plus_manual_overlay(self) -> None:
        """Manual backends overlay the preset."""
        _setup_dimensions()
        register_preset("LOCAL", {})
        result = resolve_backend_names("LOCAL", {"term": "remote-http"})
        assert result["term"] == "remote-http"
        # Rest unchanged
        assert result["ontology"] == "datacloud-data"
        assert result["execution"] == "datacloud-server"
        assert result["storage"] == "datacloud-data"

    def test_unknown_preset_raises_valueerror(self) -> None:
        """An unregistered source_type raises ValueError."""
        _setup_dimensions()
        with pytest.raises(ValueError, match="Unknown preset"):
            resolve_backend_names("NONEXISTENT", {})

    def test_manual_empty_value_is_skipped(self) -> None:
        """Empty manual values are skipped — do not clear the layer below."""
        _setup_dimensions()
        register_preset(
            "REMOTE",
            {
                "ontology": "remote-http",
                "term": "remote-http",
                "execution": "none",
                "storage": "none",
            },
        )
        # Empty string in manual should be ignored
        result = resolve_backend_names("REMOTE", {"term": ""})
        assert result["term"] == "remote-http"  # preserved from preset


class TestExtendDimensions:
    """Tests for extending backend types without breaking existing presets."""

    def test_register_new_type_presets_unaffected(self) -> None:
        """Registering a new dimension adds it to defaults but leaves existing
        preset keys unchanged."""
        _setup_dimensions()
        register_preset("LOCAL", {})
        orig_result = resolve_backend_names("LOCAL", {})

        # Register a new dimension
        register_backend_type("cache", "memory")
        # The new dimension appears in the defaults layer
        new_result = resolve_backend_names("LOCAL", {})
        assert "cache" in new_result
        assert new_result["cache"] == "memory"
        # Existing preset keys are unchanged
        for key in orig_result:
            assert new_result[key] == orig_result[key]
        assert _BACKEND_DEFAULTS["cache"] == "memory"

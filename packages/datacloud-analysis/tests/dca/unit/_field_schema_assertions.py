"""Shared assertions for field-key schema contracts in unit tests."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def assert_uses_field_key(properties: dict[str, Any], *, context: str) -> None:
    """Assert schema properties use `field` and never `field_name_cn`."""
    assert "field" in properties, f"{context} 缺少 field: {list(properties.keys())}"
    assert "field_name_cn" not in properties, (
        f"{context} 不应包含 field_name_cn: {list(properties.keys())}"
    )


def assert_required_uses_field(required: Sequence[str], *, context: str) -> None:
    """Assert required list includes `field` and excludes `field_name_cn`."""
    assert "field" in required, f"{context} required 应包含 field，实际: {list(required)}"
    assert "field_name_cn" not in required, (
        f"{context} required 不应包含 field_name_cn，实际: {list(required)}"
    )

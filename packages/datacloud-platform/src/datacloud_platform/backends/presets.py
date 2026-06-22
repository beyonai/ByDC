"""Backend preset system — register named preset combinations.

Each preset is a set of dimension→impl overrides.  Only dimensions that differ
from the defaults need to be listed.
"""

from __future__ import annotations

_PRESETS: dict[str, dict[str, str]] = {}


def register_preset(name: str, overrides: dict[str, str]) -> None:
    """Register a named preset combination.

    Args:
        name: Preset name, e.g. "LOCAL", "REMOTE".
        overrides: Dimension → impl mapping.  Only list dimensions that differ
                   from the defaults; empty dict = all defaults.

    Example:
        register_preset("LOCAL", {})
        register_preset("REMOTE", {
            "ontology":  "remote-http",
            "knowledge": "remote-http",
            "execution": "none",
            "storage":   "none",
        })
    """
    _PRESETS[name] = dict(overrides)


# ── Built-in presets ──
register_preset("LOCAL", {})
register_preset(
    "REMOTE",
    {
        "ontology": "remote-http",
        "knowledge": "remote-http",
        "execution": "none",
        "storage": "none",
    },
)

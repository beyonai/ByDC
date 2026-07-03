"""Backend preset system — register named preset combinations + built-in implementations.

Each preset is a set of dimension→impl overrides.  Only dimensions that differ
from the defaults need to be listed.

Implementations that ship with datacloud-platform (e.g. ``remote-http``)
are registered here so importing the package is enough — callers don't
register factories themselves.
"""

from __future__ import annotations

_PRESETS: dict[str, dict[str, str]] = {}

_registered_remote: bool = False


def _register_remote_implementations() -> None:
    """Register remote-http backend implementations (idempotent).

    Called at import time so ``import datacloud_platform`` auto-registers
    the REMOTE preset's required factories.
    """
    global _registered_remote
    if _registered_remote:
        return
    from datacloud_platform.adapters.remote_adapter import (  # noqa: PLC0415
        RemoteOntologyBackend,
        RemoteTermBackend,
    )
    from datacloud_platform.backends.registry import register_implementation

    register_implementation(
        "ontology", "remote-http", lambda: RemoteOntologyBackend("")
    )
    register_implementation("term", "remote-http", lambda: RemoteTermBackend(""))
    _registered_remote = True


def register_preset(name: str, overrides: dict[str, str]) -> None:
    """Register a named preset combination.

    Args:
        name: Preset name, e.g. "LOCAL", "REMOTE".
        overrides: Dimension → impl mapping.  Only list dimensions that differ
                   from the defaults; empty dict = all defaults.

    Example:
        register_preset("LOCAL", {})
        register_preset("REMOTE", {
            "ontology": "remote-http",
            "term":     "remote-http",
            "execution": "none",
            "storage":   "none",
        })
    """
    _PRESETS[name] = dict(overrides)


# ── Built-in presets ──
register_preset("LOCAL", {"term": "native-data"})
register_preset(
    "REMOTE",
    {
        "ontology": "remote-http",
        "term": "remote-http",
        "execution": "local-exec",
        "storage": "none",
    },
)
register_preset("DEFAULT", {"term": "native-data"})
register_preset("DATA_ONLY", {"term": "none"})

# Remote-http implementations are registered lazily by
# _register_remote_implementations(), called from runtime.py after
# register_backend_type() has declared the dimensions.

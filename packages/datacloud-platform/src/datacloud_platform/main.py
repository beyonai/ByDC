"""DataCloud Platform — backend registration and platform initialization.

Usage::

    from datacloud_platform.main import _init_platform
    platform = _init_platform()
    app = create_app(platform)
"""

from __future__ import annotations

from datacloud_platform.adapters.data_adapter import DataCloudDataBackend
from datacloud_platform.adapters.local_execution_adapter import LocalExecutionBackend
from datacloud_platform.adapters.none_adapters import (
    _NoopKnowledgeBackend,
    _NoopStorageBackend,
)
from datacloud_platform.api.server import create_app  # noqa: F401
from datacloud_platform.backends.presets import register_preset
from datacloud_platform.backends.registry import (
    register_backend_type,
    register_implementation,
)
from datacloud_platform.base_entry import (
    OntologyBaseRegistry,
    _default_registry_path,
)
from datacloud_platform.platform import DatacloudPlatform


def _init_platform() -> DatacloudPlatform:
    """Initialize platform with default backends and presets.

    Registers native backend types (data-adapter, local-exec) and noop fallbacks,
    then creates a DatacloudPlatform instance with an empty OntologyBaseRegistry.

    Returns:
        A fully initialized DatacloudPlatform ready for use with create_app().
    """
    # ── Register backend types ──────────────────────────────────────────
    register_backend_type("ontology", "native-data")
    register_backend_type("knowledge", "native-data")
    register_backend_type("execution", "local-exec")
    register_backend_type("storage", "native-data")

    # ── Register implementations ────────────────────────────────────────
    register_implementation("ontology", "native-data", lambda: DataCloudDataBackend())
    register_implementation("knowledge", "native-data", lambda: DataCloudDataBackend())
    register_implementation("execution", "local-exec", lambda: LocalExecutionBackend())
    register_implementation("storage", "native-data", lambda: DataCloudDataBackend())
    register_implementation("knowledge", "none", lambda: _NoopKnowledgeBackend())
    register_implementation("storage", "none", lambda: _NoopStorageBackend())

    # ── Register presets ────────────────────────────────────────────────
    register_preset(
        "DEFAULT",
        {
            "ontology": "native-data",
            "knowledge": "native-data",
            "execution": "local-exec",
            "storage": "native-data",
        },
    )
    register_preset(
        "DATA_ONLY",
        {
            "ontology": "native-data",
            "knowledge": "none",
            "execution": "none",
            "storage": "none",
        },
    )

    # ── Create platform ─────────────────────────────────────────────────
    registry = OntologyBaseRegistry.restore(_default_registry_path())
    return DatacloudPlatform(_base_registry=registry)

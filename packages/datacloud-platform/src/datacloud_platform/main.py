"""DataCloud Platform — backend registration and platform initialization.

Usage::

    from datacloud_platform.main import _init_platform
    platform = _init_platform()
    app = create_app(platform)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from datacloud_platform.platform_file_storage import _data_dir

from datacloud_platform.adapters.data_adapter import DataCloudDataBackend
from datacloud_platform.adapters.json_entity_store import JsonEntityStore
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
from datacloud_platform.base_entry import OntologyBaseRegistry
from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)

_owl_loaded_path: str | None = None


def _load_owl_if_configured(entity_store: JsonEntityStore) -> Any | None:
    """Load OWL from the configured path into the EntityStore on startup.

    Checks ``DATACLOUD_OWL_PATH`` env var.  When set, loads the OWL ontology
    and persists it as JSON objects/views/relations so downstream consumers
    (e.g. OntologyStore) have immediate access.
    """
    global _owl_loaded_path

    resolved = os.environ.get("DATACLOUD_OWL_PATH")
    if not resolved:
        return None

    owl_path = Path(resolved)
    if not owl_path.exists():
        logger.warning("DATACLOUD_OWL_PATH set but path not found: %s", owl_path)
        return None

    # Use DataCloudDataBackend's parse/save pipeline with the shared entity_store
    backend = DataCloudDataBackend(entity_store=entity_store)
    parsed = backend.parse_owl(owl_path)
    base_path = _data_dir() / "owl_default"
    counts = backend.save_parsed_content(base_path, parsed)

    _owl_loaded_path = resolved
    logger.info(
        "OWL loaded from %s: objects=%d views=%d relations=%d",
        resolved,
        counts.get("objects", 0),
        counts.get("views", 0),
        counts.get("relations", 0),
    )
    return counts


def _init_platform() -> DatacloudPlatform:
    """Initialize platform with default backends and presets.

    Registers native backend types (data-adapter, local-exec) and noop fallbacks,
    creates a shared JsonEntityStore, then builds a DatacloudPlatform with an
    OntologyBaseRegistry restored from disk.

    Returns:
        A fully initialized DatacloudPlatform ready for use with create_app().
    """
    data_dir = _data_dir()
    entity_store = JsonEntityStore(data_dir)

    # ── Register backend types ──────────────────────────────────────────
    register_backend_type("ontology", "native-data")
    register_backend_type("knowledge", "native-data")
    register_backend_type("execution", "local-exec")
    register_backend_type("storage", "native-data")

    # ── Register implementations (entity_store injected for data adapter) ──
    register_implementation(
        "ontology",
        "native-data",
        lambda es=entity_store: DataCloudDataBackend(entity_store=es),
    )
    register_implementation(
        "knowledge",
        "native-data",
        lambda es=entity_store: DataCloudDataBackend(entity_store=es),
    )
    register_implementation("execution", "local-exec", lambda: LocalExecutionBackend())
    register_implementation(
        "storage",
        "native-data",
        lambda es=entity_store: DataCloudDataBackend(entity_store=es),
    )
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
    registry = OntologyBaseRegistry(entity_store)
    registry.restore()
    platform = DatacloudPlatform(
        _base_registry=registry,
        _entity_store=entity_store,
    )

    # ── OWL startup landing ─────────────────────────────────────────────
    _load_owl_if_configured(entity_store)

    return platform

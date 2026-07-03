"""Backend registry — generic type + implementation registration with compile-time verification.

Replaces the old per-backend register_*_backend() functions with a unified
register_backend_type() + register_implementation() system (§6.1 of architecture doc).

Old per-backend functions are kept as backward-compatible wrappers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from datacloud_platform.backends.execution import ExecutionBackend
from datacloud_platform.backends.ontology import OntologyBackend
from datacloud_platform.backends.storage import StorageBackend
from datacloud_platform.backends.term import TermBackend

# ── Type aliases ──

BackendFactory = Callable[[], Any]

OntologyBackendFactory = Callable[[], OntologyBackend]
TermBackendFactory = Callable[[], TermBackend]
ExecutionBackendFactory = Callable[[], ExecutionBackend]
StorageBackendFactory = Callable[[], StorageBackend]

# ── Generic registry state ──

_BACKEND_DEFAULTS: dict[str, str] = {}
"""Dimension name → default implementation name."""

_IMPLEMENTATIONS: dict[str, dict[str, BackendFactory]] = {}
"""Dimension name → {impl_name: factory}."""


# ── Generic registration ──


def register_backend_type(name: str, default_impl: str) -> None:
    """Declare a Backend capability dimension and its default implementation.

    Args:
        name: Dimension name, e.g. "ontology", "term".
        default_impl: Default implementation name, e.g. "datacloud-data".

    Raises:
        ValueError: If this dimension is already registered.
    """
    if name in _BACKEND_DEFAULTS:
        raise ValueError(f"Backend type '{name}' already registered")
    _BACKEND_DEFAULTS[name] = default_impl
    _IMPLEMENTATIONS[name] = {}


def register_implementation(
    type_name: str, impl_name: str, factory: BackendFactory
) -> None:
    """Register an implementation factory for a dimension.

    Args:
        type_name: Dimension name.
        impl_name: Implementation name, e.g. "datacloud-data", "remote-http", "none".
        factory: Zero-arg callable returning a Backend instance.

    Raises:
        ValueError: If type_name is not a registered dimension.
        ValueError: If impl_name is already registered for this dimension.
    """
    impls = _IMPLEMENTATIONS.get(type_name)
    if impls is None:
        raise ValueError(
            f"Unknown backend type '{type_name}'. "
            f"Register it first with register_backend_type()."
        )
    if impl_name in impls:
        raise ValueError(
            f"Implementation '{impl_name}' already registered for '{type_name}'"
        )
    impls[impl_name] = factory


def get_backend_factory(type_name: str, impl_name: str) -> BackendFactory:
    """Get the factory for a dimension + implementation pair.

    Args:
        type_name: Dimension name.
        impl_name: Implementation name.

    Returns:
        The registered factory callable.

    Raises:
        KeyError: If type_name is unknown or impl_name is not registered.
    """
    impls = _IMPLEMENTATIONS.get(type_name)
    if impls is None:
        raise KeyError(f"Unknown backend type '{type_name}'")
    factory = impls.get(impl_name)
    if factory is None:
        available = ", ".join(sorted(impls))
        raise KeyError(
            f"Implementation '{impl_name}' not registered for '{type_name}'. "
            f"Available: {available}"
        )
    return factory


def verify_backend_registration() -> None:
    """Ensure every registered Backend dimension has at least one implementation.

    Called after registration is complete, before constructing DatacloudPlatform.

    Raises:
        RuntimeError: If any dimension has zero implementations.
    """
    missing: list[str] = []
    for type_name in _BACKEND_DEFAULTS:
        if not _IMPLEMENTATIONS.get(type_name):
            missing.append(type_name)
    if missing:
        raise RuntimeError(
            f"No implementations registered for backend types: {', '.join(missing)}. "
            f"Call register_implementation() before constructing DatacloudPlatform."
        )


# ── Backward-compatible per-backend helpers ──
#
# These delegate to the generic system above so existing callers keep working.
# They auto-register the dimension on first use to remain fully backward-compatible.


def _ensure_dimension(name: str) -> None:
    """Lazily register a dimension if not already registered."""
    if name not in _BACKEND_DEFAULTS:
        _BACKEND_DEFAULTS[name] = "none"
        _IMPLEMENTATIONS[name] = {}


def register_ontology_backend(name: str, factory: OntologyBackendFactory) -> None:
    """Register an OntologyBackend factory (backward-compat wrapper)."""
    _ensure_dimension("ontology")
    register_implementation("ontology", name, factory)


def register_term_backend(name: str, factory: TermBackendFactory) -> None:
    """Register a TermBackend factory (backward-compat wrapper)."""
    _ensure_dimension("term")
    register_implementation("term", name, factory)


def register_execution_backend(name: str, factory: ExecutionBackendFactory) -> None:
    """Register an ExecutionBackend factory (backward-compat wrapper)."""
    _ensure_dimension("execution")
    register_implementation("execution", name, factory)


def register_storage_backend(name: str, factory: StorageBackendFactory) -> None:
    """Register a StorageBackend factory (backward-compat wrapper)."""
    _ensure_dimension("storage")
    register_implementation("storage", name, factory)


def get_ontology_backend(name: str) -> OntologyBackend:
    """Get OntologyBackend instance by name (backward-compat wrapper)."""
    _ensure_dimension("ontology")
    return get_backend_factory("ontology", name)()  # type: ignore[no-any-return]


def get_term_backend(name: str) -> TermBackend:
    """Get TermBackend instance by name (backward-compat wrapper)."""
    _ensure_dimension("term")
    return get_backend_factory("term", name)()  # type: ignore[no-any-return]


def get_execution_backend(name: str) -> ExecutionBackend:
    """Get ExecutionBackend instance by name (backward-compat wrapper)."""
    _ensure_dimension("execution")
    return get_backend_factory("execution", name)()  # type: ignore[no-any-return]


def get_storage_backend(name: str) -> StorageBackend:
    """Get StorageBackend instance by name (backward-compat wrapper)."""
    _ensure_dimension("storage")
    return get_backend_factory("storage", name)()  # type: ignore[no-any-return]

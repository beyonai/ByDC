"""DataCloud Knowledge SDK.

该包位于 `packages/datacloud-knowledge/src/datacloud_knowledge/`。
"""

from typing import Any

__version__ = "0.2.0"

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {}


def __getattr__(name: str) -> Any:
    """Lazily import optional SDK surfaces."""

    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'datacloud_knowledge' has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "__version__",
]

"""Thread context — re-exports from datacloud-data SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_data_sdk.context import get_current_context as get_current_context
else:
    try:
        from datacloud_data_sdk.context import get_current_context
    except ImportError:

        def get_current_context() -> object:  # type: ignore[no-redef]
            """Fallback when datacloud-data is not installed."""
            raise RuntimeError(
                "datacloud-data is not installed; cannot resolve thread-local context"
            )


__all__ = ["get_current_context"]

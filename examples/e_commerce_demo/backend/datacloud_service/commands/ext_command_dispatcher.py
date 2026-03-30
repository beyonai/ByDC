"""ext_params command dispatcher."""

from __future__ import annotations

from typing import Any

from .get_file_by_page_command import handle_get_file_by_page_command
from .update_terms_name_command import handle_update_terms_name_command


def handle_ext_command(
    *,
    ext_params: dict[str, Any],
    session_id: str,
    workspace_dir: str | None,
) -> tuple[bool, dict[str, Any] | None]:
    """Handle ext_params command and return ``(handled, payload)``."""
    command = ext_params.get("command")
    if not isinstance(command, str) or not command.strip():
        return False, None

    handled, payload = handle_update_terms_name_command(ext_params=ext_params)
    if handled:
        return True, payload

    handled, payload = handle_get_file_by_page_command(
        ext_params=ext_params,
        session_id=session_id,
        workspace_dir=workspace_dir,
    )
    if handled:
        return True, payload

    return False, None


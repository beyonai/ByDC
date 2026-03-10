"""Composite backend with tenant-aware file storage."""

import asyncio
from collections.abc import Callable
from pathlib import Path

from datacloud_agent.tenant.context import TenantContext


class TenantAwareFileBackend:
    """File backend that routes operations based on tenant context and path prefixes.

    Supports three path prefixes:
    - public/: files accessible to all tenants (no tenant isolation)
    - user_public/: files specific to a tenant, readable by others
    - user_private/: files private to a tenant

    For user_public and user_private prefixes, the tenant context must be set
    (either via tenant_context_getter or the current context) to determine the
    tenant-specific subdirectory.

    Args:
        base_dir: Root directory for all storage.
        tenant_context_getter: Optional callable returning TenantContext or None.
            If not provided, uses TenantContext.get_current().
    """

    def __init__(
        self,
        base_dir: Path | str,
        tenant_context_getter: Callable[[], TenantContext | None] | None = None,
    ) -> None:
        self.base_dir = Path(base_dir).resolve()
        self._tenant_context_getter = tenant_context_getter

    def _get_tenant_context(self) -> TenantContext | None:
        """Get the current tenant context."""
        if self._tenant_context_getter is not None:
            return self._tenant_context_getter()
        return TenantContext.get_current()

    def get_full_path(self, path: str) -> Path:
        """Resolve a logical path to an absolute filesystem path.

        The path must start with one of the supported prefixes:
        - public/
        - user_public/
        - user_private/

        For user_public and user_private prefixes, the tenant context must be
        available; the tenant ID is inserted after the prefix.

        Examples:
            get_full_path("public/test.txt") -> base_dir/public/test.txt
            get_full_path("user_private/doc.txt") (tenant context with tenant_id="user_123")
                -> base_dir/user_private/user_123/doc.txt

        Args:
            path: Logical path with prefix.

        Returns:
            Absolute Path object.

        Raises:
            ValueError: If path does not start with a known prefix, or if a
                tenant‑specific prefix is used but no tenant context is available.
        """
        path = path.lstrip("/")
        if path.startswith("public/"):
            # Public files have no tenant isolation
            return self.base_dir / path
        if path.startswith("user_public/"):
            prefix = "user_public"
        elif path.startswith("user_private/"):
            prefix = "user_private"
        else:
            raise ValueError(
                f"Path must start with 'public/', 'user_public/' or 'user_private/'; got {path!r}"
            )

        # For tenant‑specific prefixes we need a tenant context
        ctx = self._get_tenant_context()
        if ctx is None:
            raise ValueError(f"Path {path!r} requires a tenant context, but none is available.")
        # Remove the prefix and the following slash
        suffix = path[len(prefix) + 1 :]  # +1 for the slash
        # Insert tenant ID between prefix and the rest of the path
        tenant_subpath = f"{prefix}/{ctx.tenant_id}/{suffix}"
        return self.base_dir / tenant_subpath

    async def read(self, path: str) -> bytes:
        """Read the contents of a file.

        Args:
            path: Logical path with prefix.

        Returns:
            File contents as bytes.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        full_path = self.get_full_path(path)
        return await asyncio.to_thread(full_path.read_bytes)

    async def write(self, path: str, content: bytes) -> None:
        """Write content to a file, creating parent directories if needed.

        Args:
            path: Logical path with prefix.
            content: Bytes to write.
        """
        full_path = self.get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(full_path.write_bytes, content)

    async def exists(self, path: str) -> bool:
        """Check whether a file exists.

        Args:
            path: Logical path with prefix.

        Returns:
            True if the file exists.
        """
        full_path = self.get_full_path(path)
        return await asyncio.to_thread(full_path.exists)

    async def list_dir(self, path: str) -> list[str]:
        """List entries in a directory.

        Args:
            path: Logical path with prefix (must refer to a directory).

        Returns:
            List of entry names (files and directories) in the directory.
            If the directory does not exist, returns an empty list.

        Raises:
            NotADirectoryError: If the path exists but is not a directory.
        """
        full_path = self.get_full_path(path)
        # Check existence
        if not await asyncio.to_thread(full_path.exists):
            return []
        # Ensure it's a directory
        if not await asyncio.to_thread(full_path.is_dir):
            raise NotADirectoryError(f"{full_path} is not a directory")
        # List entries, returning only the names (not full paths)
        entries = await asyncio.to_thread(list, full_path.iterdir())
        return [entry.name for entry in entries]

"""Abstract result-file storage for exported user-visible artifacts."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ResultFileStorage(ABC):
    """Storage abstraction for persistent result files."""

    @property
    @abstractmethod
    def storage_type(self) -> str:
        """Return the backend type name."""

    @abstractmethod
    def write_text(self, file_path: str, content: str) -> str:
        """Write full text content to a logical file path."""

    @abstractmethod
    def append_text(self, file_path: str, content: str) -> str:
        """Append text content to a logical file path."""

    @abstractmethod
    def read_text(self, file_path: str, begin_line: int = 0, end_line: int = -1) -> str | None:
        """Read text content from a logical file path."""

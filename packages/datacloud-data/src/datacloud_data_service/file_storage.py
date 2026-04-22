"""Factories for persistent result-file storage backends."""

from __future__ import annotations

from datacloud_data_sdk.file_storage import LocalResultFileStorage
from datacloud_data_sdk.file_storage.base import ResultFileStorage

from datacloud_data_service.config import Settings


def build_result_file_storage(settings: Settings) -> ResultFileStorage:
    """Build the local result-file storage backend."""
    return LocalResultFileStorage(settings.result_file_base_dir or settings.csv_base_dir)

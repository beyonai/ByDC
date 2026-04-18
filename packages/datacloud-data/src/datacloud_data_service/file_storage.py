"""Factories for persistent result-file storage backends."""

from __future__ import annotations

from datacloud_data_sdk.file_storage import ApiResultFileStorage, LocalResultFileStorage
from datacloud_data_sdk.file_storage.base import ResultFileStorage

from datacloud_data_service.config import Settings


def build_result_file_storage(settings: Settings) -> ResultFileStorage:
    """Build the configured result-file storage backend."""
    storage_type = settings.result_file_storage_type.lower().strip()
    if storage_type == "api":
        if not settings.result_file_api_base_url.strip():
            raise ValueError("DATACLOUD_RESULT_FILE_API_BASE_URL is required for api storage")
        return ApiResultFileStorage(
            base_url=settings.result_file_api_base_url,
            write_txt_path=settings.result_file_api_write_txt_path,
            append_txt_path=settings.result_file_api_append_txt_path,
            read_path=settings.result_file_api_read_path,
            timeout=settings.result_file_api_timeout,
        )
    return LocalResultFileStorage(settings.result_file_base_dir or settings.csv_base_dir)

"""Pluggable storage backends for persistent result files."""

from datacloud_data_sdk.file_storage.base import ResultFileStorage
from datacloud_data_sdk.file_storage.local import LocalResultFileStorage

__all__ = [
    "LocalResultFileStorage",
    "ResultFileStorage",
]

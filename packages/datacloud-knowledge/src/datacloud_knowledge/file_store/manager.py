from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from datacloud_knowledge.file_store.backends.local import LocalFileBackend, _safe_directory
from datacloud_knowledge.file_store.errors import BackendMisconfiguredError, InvalidUploadItemError
from datacloud_knowledge.file_store.hashing import md5_of_stream
from datacloud_knowledge.file_store.types import DownloadResult, UploadItemDict, UploadResult

if TYPE_CHECKING:
    from datacloud_knowledge.file_store.backends.base import FileStorageBackend
    from datacloud_knowledge.file_store.settings import FileStoreSettings


class FileManager:
    def __init__(
        self,
        backend: FileStorageBackend,
        public_base_url: str = "",
        download_path_prefix: str = "/files",
        default_directory: str = "default",
    ):
        self.backend = backend
        self.public_base_url = public_base_url.rstrip("/")
        self.download_path_prefix = "/" + download_path_prefix.strip("/")
        self.default_directory = _safe_directory(default_directory)

    @classmethod
    def from_settings(cls, settings: FileStoreSettings) -> FileManager:
        driver = (settings.storage_driver or "").lower().strip() or None

        should_s3 = False
        if driver == "s3":
            should_s3 = True
        elif driver == "local":
            should_s3 = False
        else:
            should_s3 = bool(
                settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key
            )

        if should_s3:
            if not (
                settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key
            ):
                raise BackendMisconfiguredError(
                    "S3 driver selected but missing required S3 settings"
                )
            from datacloud_knowledge.file_store.backends.s3 import S3Backend  # noqa: PLC0415

            backend: FileStorageBackend = S3Backend.from_settings(settings)
        else:
            backend = LocalFileBackend(root_dir=settings.local_root)

        return cls(
            backend=backend,
            public_base_url=settings.public_base_url,
            download_path_prefix=settings.download_path_prefix,
            default_directory=settings.default_directory,
        )

    def build_download_url(self, md5: str, directory: str) -> str:
        directory = _safe_directory(directory)
        path = f"{self.download_path_prefix}/{directory}/{md5}"
        if not self.public_base_url:
            return path
        return f"{self.public_base_url}{path}"

    def upload_many(self, items: list[UploadItemDict]) -> list[UploadResult]:
        return [self._upload_one(item) for item in items]

    def _upload_one(self, item: UploadItemDict) -> UploadResult:
        directory = _safe_directory(item.get("directory") or self.default_directory)

        if item.get("path"):
            path = Path(item["path"])
            filename = item.get("filename") or path.name
            content_type = item.get("content_type")
            size = path.stat().st_size
            with path.open("rb") as f:
                md5 = md5_of_stream(f)
                f.seek(0)
                outcome = self.backend.put(
                    directory=directory,
                    md5=md5,
                    stream=f,
                    meta={"filename": filename, "content_type": content_type, "size": size},
                )
        elif "stream" in item and item["stream"] is not None:
            stream = item["stream"]
            stream_filename: str | None = item.get("filename")
            if not stream_filename:
                raise InvalidUploadItemError("stream upload requires filename")
            content_type = item.get("content_type")

            md5 = md5_of_stream(stream)
            size = _try_get_stream_size(stream)
            outcome = self.backend.put(
                directory=directory,
                md5=md5,
                stream=stream,
                meta={"filename": stream_filename, "content_type": content_type, "size": size},
            )
        else:
            raise InvalidUploadItemError("upload item must include path or stream")

        meta = self.backend.get_meta(md5)
        canonical_directory = str(meta.get("directory") or outcome.canonical_directory)
        download_url = self.build_download_url(md5=md5, directory=canonical_directory)
        return UploadResult(
            md5=md5,
            download_url=download_url,
            size=int(meta["size"]),
            filename=str(meta["filename"]),
            content_type=meta.get("content_type"),
            directory=canonical_directory,
            deduplicated=not outcome.wrote_content,
        )

    def download_many(self, md5_list: list[str]) -> list[DownloadResult]:
        results: list[DownloadResult] = []
        for md5 in md5_list:
            try:
                stream, meta = self.backend.get(md5)
            except Exception:
                results.append(DownloadResult(md5=md5, found=False))
                continue
            results.append(
                DownloadResult(
                    md5=md5,
                    found=True,
                    filename=meta.get("filename"),
                    content_type=meta.get("content_type"),
                    size=meta.get("size"),
                    directory=meta.get("directory"),
                    stream=stream,
                )
            )
        return results


def _try_get_stream_size(stream: BinaryIO) -> int:
    try:
        pos = stream.tell()
        stream.seek(0, os.SEEK_END)
        end = stream.tell()
        stream.seek(pos)
        return int(end)
    except Exception:
        return -1

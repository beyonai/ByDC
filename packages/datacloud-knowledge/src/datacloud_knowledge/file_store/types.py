from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, BinaryIO, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class UploadItemDict(TypedDict, total=False):
    # one of:
    path: str
    stream: BinaryIO

    # required for stream upload
    filename: str

    # optional
    content_type: str
    directory: str


class FileMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    content_type: str | None = None
    size: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    directory: str


class UploadResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    md5: str
    download_url: str
    size: int
    filename: str
    content_type: str | None = None
    directory: str
    deduplicated: bool


class DownloadResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    md5: str
    found: bool
    filename: str | None = None
    content_type: str | None = None
    size: int | None = None
    directory: str | None = None
    # 文件样对象（例如 open(..., "rb") 返回值、或 S3 StreamingBody），运行时类型不做强校验
    stream: Any | None = None


class PutOutcome(BaseModel):
    """Backend put result.

    - wrote_content: 是否写入了内容对象（False 表示已存在，仅可能写入 ref）
    - canonical_directory: 该 md5 的 canonical directory
    """

    model_config = ConfigDict(extra="forbid")

    wrote_content: bool
    canonical_directory: str


JsonDict = dict[str, Any]

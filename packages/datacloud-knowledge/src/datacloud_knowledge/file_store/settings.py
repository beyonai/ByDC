from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FileStoreSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FILE_", extra="ignore")

    storage_driver: str | None = Field(default=None, description="s3|local")

    public_base_url: str = ""
    download_path_prefix: str = "/files"
    default_directory: str = "default"

    # Local
    local_root: str = "./.datacloud_files"

    # S3
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None


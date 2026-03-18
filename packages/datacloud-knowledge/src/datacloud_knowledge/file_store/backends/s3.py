from __future__ import annotations

import json
from typing import BinaryIO

from ..errors import BackendMisconfigured, FileNotFoundInStore
from ..settings import FileStoreSettings
from ..types import JsonDict, PutOutcome
from .local import _safe_directory, _shard


class S3Backend:
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str | None,
        access_key_id: str,
        secret_access_key: str,
    ):
        if not bucket:
            raise BackendMisconfigured("Missing s3 bucket")

        self.bucket = bucket
        self.client = _create_s3_client(
            endpoint_url=endpoint_url,
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )

    @classmethod
    def from_settings(cls, settings: FileStoreSettings) -> "S3Backend":
        if not (settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key):
            raise BackendMisconfigured("Missing required S3 settings")
        return cls(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
        )

    def exists(self, md5: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._index_key(md5))
            return True
        except Exception as e:
            ClientError = _client_error_type()
            if ClientError is not None and isinstance(e, ClientError):
                if e.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                    return False
                code = e.response.get("Error", {}).get("Code")
                if code in {"404", "NoSuchKey", "NotFound"}:
                    return False
                raise
            raise

    def put(self, directory: str, md5: str, stream: BinaryIO, meta: JsonDict) -> PutOutcome:
        directory = _safe_directory(directory)

        # Check index existence (global md5)
        index_key = self._index_key(md5)
        try:
            index = self._read_index(md5)
            canonical = str(index["canonical_directory"])
            if directory != canonical:
                self._put_ref(directory=directory, md5=md5, canonical_directory=canonical)
            return PutOutcome(wrote_content=False, canonical_directory=canonical)
        except FileNotFoundInStore:
            pass

        # First write: put content under this directory, then index
        content_key = self._content_key(directory=directory, md5=md5)

        extra_args: dict[str, object] = {}
        if meta.get("content_type"):
            extra_args["ContentType"] = str(meta["content_type"])

        self.client.upload_fileobj(stream, self.bucket, content_key, ExtraArgs=extra_args or None)

        index_obj = {"canonical_directory": directory, "meta": {**meta, "directory": directory}}
        self.client.put_object(
            Bucket=self.bucket,
            Key=index_key,
            Body=json.dumps(index_obj, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        return PutOutcome(wrote_content=True, canonical_directory=directory)

    def get(self, md5: str) -> tuple[BinaryIO, JsonDict]:
        index = self._read_index(md5)
        canonical = str(index["canonical_directory"])
        meta = dict(index["meta"])

        content_key = self._content_key(directory=canonical, md5=md5)
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=content_key)
        except Exception as e:
            ClientError = _client_error_type()
            if ClientError is not None and isinstance(e, ClientError):
                code = e.response.get("Error", {}).get("Code")
                if code in {"NoSuchKey", "NotFound", "404"}:
                    raise FileNotFoundInStore(md5) from e
            raise

        body = resp["Body"]
        return body, meta

    def get_meta(self, md5: str) -> JsonDict:
        index = self._read_index(md5)
        return dict(index["meta"])

    def _index_key(self, md5: str) -> str:
        aa, bb = _shard(md5)
        return f"index/{aa}/{bb}/{md5}.json"

    def _content_key(self, directory: str, md5: str) -> str:
        aa, bb = _shard(md5)
        directory = _safe_directory(directory)
        return f"{directory}/objects/{aa}/{bb}/{md5}"

    def _ref_key(self, directory: str, md5: str) -> str:
        aa, bb = _shard(md5)
        directory = _safe_directory(directory)
        return f"{directory}/refs/{aa}/{bb}/{md5}.json"

    def _put_ref(self, directory: str, md5: str, canonical_directory: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._ref_key(directory, md5),
            Body=json.dumps({"canonical_directory": canonical_directory}, ensure_ascii=False, indent=2).encode(
                "utf-8"
            ),
            ContentType="application/json",
        )

    def _read_index(self, md5: str) -> JsonDict:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=self._index_key(md5))
        except Exception as e:
            ClientError = _client_error_type()
            if ClientError is not None and isinstance(e, ClientError):
                code = e.response.get("Error", {}).get("Code")
                if code in {"NoSuchKey", "NotFound", "404"}:
                    raise FileNotFoundInStore(md5) from e
            raise
        body = resp["Body"].read()
        return json.loads(body.decode("utf-8"))


def _create_s3_client(
    *,
    endpoint_url: str | None,
    region: str | None,
    access_key_id: str,
    secret_access_key: str,
):
    try:
        import boto3  # type: ignore
    except Exception as e:  # pragma: no cover
        raise BackendMisconfigured("boto3 is required for S3 backend") from e

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        region_name=region or None,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )


def _client_error_type():
    try:
        from botocore.exceptions import ClientError  # type: ignore

        return ClientError
    except Exception:  # pragma: no cover
        return None


"""HTTP API-backed persistent result-file storage implementation."""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.context import get_current_context
from datacloud_data_sdk.exceptions import DatacloudError
from datacloud_data_sdk.file_storage.base import ResultFileStorage
from datacloud_data_sdk.file_storage.scoped_paths import normalize_logical_file_path


class ApiResultFileStorage(ResultFileStorage):
    """Store exported result files through a remote text-file API."""

    def __init__(
        self,
        *,
        base_url: str,
        write_txt_path: str = "/writeTxt",
        append_txt_path: str = "/appendTxt",
        read_path: str = "/read",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._write_txt_path = write_txt_path
        self._append_txt_path = append_txt_path
        self._read_path = read_path
        self._timeout = timeout

    @property
    def storage_type(self) -> str:
        return "api"

    def write_text(self, file_path: str, content: str) -> str:
        payload = {
            **self._build_context_payload(),
            "filePath": str(normalize_logical_file_path(file_path)),
            "content": content,
        }
        data = self._post_json(self._write_txt_path, payload)
        stored_path = self._extract_string(data, "filePath")
        return stored_path or file_path

    def append_text(self, file_path: str, content: str) -> str:
        payload = {
            **self._build_context_payload(),
            "filePath": str(normalize_logical_file_path(file_path)),
            "content": content,
        }
        data = self._post_json(self._append_txt_path, payload)
        stored_path = self._extract_string(data, "filePath")
        return stored_path or file_path

    def read_text(self, file_path: str, begin_line: int = 0, end_line: int = -1) -> str | None:
        payload = {
            **self._build_context_payload(),
            "filePath": str(normalize_logical_file_path(file_path)),
            "fileType": "txt",
            "begin_line": begin_line,
            "end_line": end_line,
        }
        data = self._post_json(self._read_path, payload)
        if isinstance(data, str):
            return data
        return self._extract_string(data, "content")

    def _post_json(self, path: str, payload: dict[str, Any]) -> Any:
        import httpx

        headers = self._build_headers()
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(f"{self._base_url}{path}", json=payload, headers=headers)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            return response.text

    def _build_context_payload(self) -> dict[str, str]:
        try:
            ctx = get_current_context()
        except Exception as exc:
            raise DatacloudError(
                "InvocationContext is required for API result-file storage"
            ) from exc

        user_code = str(getattr(ctx, "user_id", "") or "").strip()
        session_id = str(getattr(ctx, "session_id", "") or "").strip()
        if not user_code:
            raise DatacloudError("user_id is required for API result-file storage")
        if not session_id:
            raise DatacloudError("session_id is required for API result-file storage")
        return {
            "userCode": user_code,
            "sessionId": session_id,
        }

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        try:
            ctx = get_current_context()
        except Exception:
            return headers
        token = str(getattr(ctx, "token", "") or "").strip()
        system_code = str(getattr(ctx, "system_code", "") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if system_code:
            headers["X-System-Code"] = system_code
        return headers

    def _extract_string(self, data: Any, key: str) -> str | None:
        if isinstance(data, dict):
            value = data.get(key)
            if isinstance(value, str):
                return value
            nested = data.get("data")
            if isinstance(nested, dict):
                nested_value = nested.get(key)
                if isinstance(nested_value, str):
                    return nested_value
        return None

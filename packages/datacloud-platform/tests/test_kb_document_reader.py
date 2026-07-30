from __future__ import annotations

from typing import Any

import pytest

from datacloud_platform.services.kb_document_reader import (
    KbDocumentReadError,
    KbDocumentReader,
    build_default_kb_document_reader,
)


def test_kb_document_reader_gets_byclaw_download_and_returns_markdown() -> None:
    captured: dict[str, Any] = {}

    def get_bytes(
        path: str,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> bytes:
        captured["path"] = path
        captured["params"] = params
        captured["headers"] = headers
        return "# 本体论\n\n现有正文".encode()

    reader = KbDocumentReader(get_bytes=get_bytes)

    content = reader.read_text(
        resource_id="1234567890",
        file_path="/Methodology/本体论.md",
    )

    assert content == "# 本体论\n\n现有正文"
    assert captured["path"] == "/byaiService/datasetController/download"
    assert captured["params"] == {
        "resourceId": 1234567890,
        "directoryPath": "/Methodology/本体论.md",
    }


def test_default_reader_uses_be_domainname_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATACLOUD_KB_READ_SERVICE_NAME", raising=False)
    monkeypatch.delenv("DATACLOUD_RESULT_FILE_SERVICE_NAME", raising=False)
    monkeypatch.setenv("BE_DOMAINNAME", "ByaiService")
    monkeypatch.setenv("QA_DOMAINNAME", "byclaw-qa-manager")

    reader = build_default_kb_document_reader()

    assert reader.service_name == "ByaiService"


def test_kb_document_reader_requires_resource_id() -> None:
    reader = KbDocumentReader(get_bytes=lambda _path, _params, _headers: b"unused")

    with pytest.raises(KbDocumentReadError, match="kb_resource_id is required"):
        reader.read_text(resource_id="", file_path="/Methodology/本体论.md")

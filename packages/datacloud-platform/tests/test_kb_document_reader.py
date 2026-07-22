from __future__ import annotations

from typing import Any

import pytest

from datacloud_platform.services.kb_document_reader import (
    KbDocumentReadError,
    KbDocumentReader,
    build_default_kb_document_reader,
)


def test_kb_document_reader_posts_read_file_request_and_returns_markdown() -> None:
    captured: dict[str, Any] = {}

    def post_json(
        path: str,
        body: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        captured["path"] = path
        captured["body"] = body
        captured["headers"] = headers
        return {
            "resultCode": "0",
            "resultMsg": "success",
            "resultObject": {
                "knCode": "97",
                "filePath": "/Methodology/本体论.md",
                "data": "# 本体论\n\n现有正文",
                "reachedEof": True,
            },
        }

    reader = KbDocumentReader(post_json=post_json)

    content = reader.read_text(
        kn_code="97",
        file_path="/Methodology/本体论.md",
    )

    assert content == "# 本体论\n\n现有正文"
    assert captured["path"] == "/api/v1/readFile"
    assert captured["body"] == {
        "knCode": "97",
        "filePath": "/Methodology/本体论.md",
    }


def test_default_reader_uses_qa_domainname(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATACLOUD_KB_READ_SERVICE_NAME", raising=False)
    monkeypatch.delenv("DATACLOUD_RESULT_FILE_SERVICE_NAME", raising=False)
    monkeypatch.setenv("BE_DOMAINNAME", "ByaiService")
    monkeypatch.setenv("QA_DOMAINNAME", "byclaw-qa-manager")

    reader = build_default_kb_document_reader()

    assert reader.service_name == "byclaw-qa-manager"


def test_kb_document_reader_raises_on_non_zero_result_code() -> None:
    def post_json(
        path: str,
        body: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        return {
            "resultCode": "-1",
            "resultMsg": "file not found: /Methodology/本体论.md",
            "resultObject": {},
        }

    reader = KbDocumentReader(post_json=post_json)

    with pytest.raises(KbDocumentReadError, match="file not found"):
        reader.read_text(kn_code="97", file_path="/Methodology/本体论.md")

"""单元测试：本体术语创建接口中 OWL 文件上传逻辑。

覆盖三种场景：
  1. 附带 owl_file → 上传文件，以 md5 作为 owl_doc_id
  2. 不传文件只传 owl_doc_id → 不调用 FileManager，直接使用表单值
  3. 同时传 owl_file 和 owl_doc_id → 文件上传结果优先，表单值被忽略
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import datacloud_knowledge.knowledge_build.ontology.service as svc_module
import pytest
from datacloud_knowledge.file_store.types import UploadResult
from datacloud_knowledge.knowledge_build.deps import get_file_manager
from datacloud_knowledge.knowledge_build.ontology.router import router
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

_FAKE_MD5 = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
_OWL_CONTENT = b"<owl:Ontology>...</owl:Ontology>"


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_file_manager() -> MagicMock:
    """返回预设上传结果的 FileManager Mock。"""
    fm = MagicMock()
    fm.upload_many.return_value = [
        UploadResult(
            md5=_FAKE_MD5,
            download_url=f"/files/ontology/{_FAKE_MD5}",
            size=len(_OWL_CONTENT),
            filename="view.owl",
            directory="ontology",
            deduplicated=False,
        )
    ]
    return fm


@pytest.fixture
def mock_service(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """将 service.create_ontology_term 替换为 AsyncMock，避免 NotImplementedError。"""
    m: AsyncMock = AsyncMock(
        return_value={
            "term_id": "TERM_VIEW_001",
            "term_name": "员工视图",
            "term_type_code": "VIEW",
        }
    )
    monkeypatch.setattr(svc_module, "create_ontology_term", m)
    return m


@pytest.fixture
def app(mock_file_manager: MagicMock) -> FastAPI:
    """组装最小 FastAPI 应用，注入 Mock FileManager。"""
    _app = FastAPI()
    _app.include_router(router)
    _app.dependency_overrides[get_file_manager] = lambda: mock_file_manager
    return _app


# ── 测试用例 ───────────────────────────────────────────────────────────────────


async def test_create_term_with_owl_file_uploads_and_sets_owl_doc_id(
    app: FastAPI,
    mock_file_manager: MagicMock,
    mock_service: AsyncMock,
) -> None:
    """owl_file 存在时：上传文件，以 md5 覆盖 owl_doc_id 后调用 service。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/ontology/terms",
            data={
                "term_name": "员工视图",
                "term_type_code": "VIEW",
                "domain_id": "DOMAIN_001",
            },
            files={"owl_file": ("view.owl", _OWL_CONTENT, "application/owl+xml")},
        )

    assert resp.status_code == 200
    assert resp.json()["term_id"] == "TERM_VIEW_001"

    # FileManager.upload_many 被调用一次
    mock_file_manager.upload_many.assert_called_once()
    upload_item = mock_file_manager.upload_many.call_args[0][0][0]
    assert upload_item["filename"] == "view.owl"
    assert upload_item["directory"] == "ontology"

    # service 收到的 owl_doc_id 是上传结果的 md5，而非表单原值
    mock_service.assert_awaited_once()
    assert mock_service.call_args.kwargs["owl_doc_id"] == _FAKE_MD5


async def test_create_term_without_file_skips_upload(
    app: FastAPI,
    mock_file_manager: MagicMock,
    mock_service: AsyncMock,
) -> None:
    """不传文件时：FileManager 不被调用，owl_doc_id 直接取表单值。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/ontology/terms",
            data={
                "term_name": "员工",
                "term_type_code": "OBJ",
                "domain_id": "DOMAIN_001",
                "owl_doc_id": "existing-file-id",
            },
        )

    assert resp.status_code == 200
    mock_file_manager.upload_many.assert_not_called()
    assert mock_service.call_args.kwargs["owl_doc_id"] == "existing-file-id"


async def test_owl_file_overrides_form_owl_doc_id(
    app: FastAPI,
    mock_file_manager: MagicMock,
    mock_service: AsyncMock,
) -> None:
    """同时传 owl_file 和 owl_doc_id 时：上传结果优先，表单值被忽略。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/ontology/terms",
            data={
                "term_name": "动作A",
                "term_type_code": "ACTION",
                "domain_id": "DOMAIN_001",
                "owl_doc_id": "stale-id",
            },
            files={"owl_file": ("action.owl", _OWL_CONTENT, "text/turtle")},
        )

    assert resp.status_code == 200
    mock_file_manager.upload_many.assert_called_once()
    # service 收到的应是 md5，而非 "stale-id"
    assert mock_service.call_args.kwargs["owl_doc_id"] == _FAKE_MD5

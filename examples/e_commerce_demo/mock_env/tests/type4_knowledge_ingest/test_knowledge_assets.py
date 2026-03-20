"""Type4: 知识构建测试套件。

测试分层：
  [unit]       — 不依赖数据库，只需文件系统
  [api-unit]   — 使用 TestClient，不依赖数据库（precheck 全内存）
  [integration]— 依赖真实数据库，需 DATACLOUD_ENABLE_INTEGRATION_TESTS=1
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ════════════════════════════════════════════════════════════════════════════
# 1. 文件存在性（unit）
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.type4_knowledge
def test_knowledge_dirs_exist(resource_knowledge_dir: Path) -> None:
    """知识资源根目录必须存在。"""
    assert resource_knowledge_dir.exists(), (
        f"知识资源根目录不存在: {resource_knowledge_dir}"
    )


@pytest.mark.type4_knowledge
def test_import_package_structure(import_package_path: Path) -> None:
    """import_package 目录若存在，manifest.json 必须存在且列出的文件均存在。"""
    if not import_package_path.exists():
        pytest.skip("import_package/ 目录不存在，跳过")

    manifest_path = import_package_path / "manifest.json"
    assert manifest_path.exists(), "manifest.json 缺失"

    import json
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for step in manifest.get("import_steps", []):
        file_rel = step.get("file", "")
        if not file_rel:
            continue
        file_path = import_package_path / file_rel
        assert file_path.exists(), (
            f"manifest 中声明的文件不存在: {file_rel}"
        )


@pytest.mark.type4_knowledge
def test_dict_terms_nonempty(import_package_path: Path) -> None:
    """dict_terms.jsonl 应存在且非空。"""
    if not import_package_path.exists():
        pytest.skip("import_package/ 目录不存在，跳过")
    path = import_package_path / "terms" / "dict_terms.jsonl"
    if not path.exists():
        pytest.skip("dict_terms.jsonl 不存在，跳过")
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) > 0, "dict_terms.jsonl 内容为空"


@pytest.mark.type4_knowledge
def test_list_terms_nonempty(import_package_path: Path) -> None:
    """list_terms.jsonl 应存在且非空。"""
    if not import_package_path.exists():
        pytest.skip("import_package/ 目录不存在，跳过")
    path = import_package_path / "terms" / "list_terms.jsonl"
    if not path.exists():
        pytest.skip("list_terms.jsonl 不存在，跳过")
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) > 0, "list_terms.jsonl 内容为空"


@pytest.mark.type4_knowledge
def test_terms_domain_and_library(import_package_path: Path) -> None:
    """所有术语的 domain_code 应为 DOMAIN_002，library_code 应为 LIB_002。"""
    import json
    if not import_package_path.exists():
        pytest.skip("import_package/ 目录不存在，跳过")

    for fname in ("dict_terms.jsonl", "list_terms.jsonl"):
        path = import_package_path / "terms" / fname
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            assert obj.get("domain_code") == "DOMAIN_002", (
                f"{fname}:{i} domain_code={obj.get('domain_code')} (expected DOMAIN_002)"
            )
            assert obj.get("library_code") == "LIB_002", (
                f"{fname}:{i} library_code={obj.get('library_code')} (expected LIB_002)"
            )


# ════════════════════════════════════════════════════════════════════════════
# 2. 知识包预检 API（api-unit，不写库）
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.type4_knowledge
def test_precheck_passes(knowledge_client, import_package_path: Path) -> None:
    """对 e_commerce_demo import_package 调用预检接口，期望全部通过。"""
    resp = knowledge_client.post(
        "/build/import-package/precheck",
        json={"folder_path": str(import_package_path)},
    )
    assert resp.status_code == 200, f"HTTP error: {resp.text}"
    body = resp.json()
    assert body["status"] == "ok", (
        f"预检失败，共 {len(body.get('errors', []))} 条错误：\n"
        + "\n".join(
            f"  {e['file']}:{e.get('line','?')} — {e['error']}"
            for e in body.get("errors", [])
        )
    )
    assert body["total_rows"] > 0, "预检通过但 total_rows=0，数据文件可能为空"


@pytest.mark.type4_knowledge
def test_precheck_returns_file_list(knowledge_client, import_package_path: Path) -> None:
    """预检结果中应包含每个文件的摘要信息。"""
    resp = knowledge_client.post(
        "/build/import-package/precheck",
        json={"folder_path": str(import_package_path)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["files"], list)
    assert len(body["files"]) > 0
    for f in body["files"]:
        assert "file" in f
        assert "rows" in f


@pytest.mark.type4_knowledge
def test_precheck_nonexistent_folder(knowledge_client) -> None:
    """传入不存在的文件夹时预检应返回 failed。"""
    resp = knowledge_client.post(
        "/build/import-package/precheck",
        json={"folder_path": "/nonexistent/path/that/does/not/exist"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert len(body["errors"]) > 0


# ════════════════════════════════════════════════════════════════════════════
# 3. 知识构建通知接口（api-unit）
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.type4_knowledge
def test_notify_endpoint_success_payload(notify_client) -> None:
    """向 mock_env 通知接口推送成功结果，应返回 ack=True。"""
    notify_client.delete("/api/v1/knowledge/ingest/notify/latest")

    payload = {
        "status": "success",
        "folder_path": "/data/test_package",
        "stats": {
            "domains":   {"inserted": 2, "updated": 0, "deleted": 0},
            "libraries": {"inserted": 2, "updated": 0, "deleted": 0},
            "terms":     {"inserted": 16107, "updated": 0, "deleted": 0},
            "relations": {"inserted": 0, "updated": 0, "deleted": 0},
        },
    }
    resp = notify_client.post("/api/v1/knowledge/ingest/notify", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ack"] is True
    assert body["status"] == "success"


@pytest.mark.type4_knowledge
def test_notify_endpoint_precheck_failed_payload(notify_client) -> None:
    """向通知接口推送预检失败结果，应正确存储错误信息。"""
    notify_client.delete("/api/v1/knowledge/ingest/notify/latest")

    payload = {
        "status": "precheck_failed",
        "folder_path": "/data/bad_package",
        "precheck_errors": [
            {"file": "terms/bad.jsonl", "line": 3, "error": "缺少必填字段: domain_code"},
        ],
    }
    resp = notify_client.post("/api/v1/knowledge/ingest/notify", json=payload)
    assert resp.status_code == 200
    assert resp.json()["ack"] is True


@pytest.mark.type4_knowledge
def test_notify_latest_reflects_last_push(notify_client) -> None:
    """推送通知后，/notify/latest 应返回最新一条。"""
    notify_client.delete("/api/v1/knowledge/ingest/notify/latest")

    payload = {"status": "success", "folder_path": "/data/pkg_v2"}
    notify_client.post("/api/v1/knowledge/ingest/notify", json=payload)

    resp = notify_client.get("/api/v1/knowledge/ingest/notify/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["folder_path"] == "/data/pkg_v2"
    assert "received_at" in body


@pytest.mark.type4_knowledge
def test_notify_clear(notify_client) -> None:
    """清除通知后，/notify/latest 应返回空对象。"""
    notify_client.post(
        "/api/v1/knowledge/ingest/notify",
        json={"status": "success", "folder_path": "/data/temp"},
    )
    notify_client.delete("/api/v1/knowledge/ingest/notify/latest")

    resp = notify_client.get("/api/v1/knowledge/ingest/notify/latest")
    assert resp.status_code == 200
    assert resp.json() == {}


# ════════════════════════════════════════════════════════════════════════════
# 4. 完整导入 + 回调集成测试（需真实数据库）
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.type4_knowledge
@pytest.mark.integration
def test_run_with_callback(
    db_ready,
    knowledge_client,
    notify_client,
    import_package_path: Path,
    integration_enabled: bool,
) -> None:
    """完整流程：预检 → 入库 → 回调通知。

    需要：
      - 真实 PostgreSQL/OpenGauss 数据库（环境变量 DB_HOST 等配置正确）
      - DATACLOUD_ENABLE_INTEGRATION_TESTS=1
    """
    if not integration_enabled:
        pytest.skip("integration tests disabled (set DATACLOUD_ENABLE_INTEGRATION_TESTS=1)")

    notify_client.delete("/api/v1/knowledge/ingest/notify/latest")

    resp = knowledge_client.post(
        "/build/import-package/run",
        json={
            "folder_path": str(import_package_path),
            "callback": None,
        },
    )
    assert resp.status_code == 200, f"run 失败: {resp.text}"
    body = resp.json()
    assert body["status"] == "success", (
        f"导入失败: error={body.get('error')}\n"
        f"precheck_errors={body.get('precheck_errors')}"
    )

    stats = body.get("stats", {})

    def _touched(entity: str) -> int:
        s = stats.get(entity, {})
        return s.get("inserted", 0) + s.get("updated", 0)

    assert _touched("domains") > 0, f"domains 无写入: {stats.get('domains')}"
    assert _touched("terms") > 0, f"terms 无写入: {stats.get('terms')}"

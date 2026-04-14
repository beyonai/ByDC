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
    """知识资源根目录必须存在。

    各子目录（ontology / terminology / base / import_package）按需存在，
    允许只包含本次变更涉及的文件，无需全部齐备。
    """
    assert resource_knowledge_dir.exists(), f"知识资源根目录不存在: {resource_knowledge_dir}"


@pytest.mark.type4_knowledge
def test_ontology_subdirs_nonempty(resource_knowledge_dir: Path) -> None:
    """ontology/ 目录若存在，其各子目录（objects / views / actions / functions）应非空。

    若 ontology/ 整个目录不存在（本次变更不涉及本体），直接跳过。
    """
    onto_dir = resource_knowledge_dir / "ontology"
    if not onto_dir.exists():
        pytest.skip("ontology/ 目录不存在，本次变更不涉及本体，跳过")

    for subdir in ("objects", "views", "actions", "functions"):
        d = onto_dir / subdir
        if d.exists():
            assert any(d.glob("*.json")), f"ontology/{subdir}/ 目录存在但没有 JSON 文件"


@pytest.mark.type4_knowledge
def test_terminology_files_nonempty(resource_knowledge_dir: Path) -> None:
    """base/ 和 terminology/ 目录若存在，其核心 CSV 文件应存在。

    目录布局：
      base/        — domain.csv / term_library.csv / term_type.csv（低频基础配置）
      terminology/ — term.csv / term_relation.csv / term_data.csv（高频术语数据）

    两个目录均不存在时跳过（本次变更不涉及 CSV 术语数据）。
    """
    base_dir = resource_knowledge_dir / "base"
    term_dir = resource_knowledge_dir / "terminology"

    if not base_dir.exists() and not term_dir.exists():
        pytest.skip("base/ 和 terminology/ 目录均不存在，本次变更不涉及 CSV 术语数据，跳过")

    if base_dir.exists():
        for file_name in ("domain.csv", "term_type.csv", "term_library.csv"):
            assert (base_dir / file_name).exists(), f"missing base file: {file_name}"

    if term_dir.exists():
        for file_name in ("term.csv", "term_relation.csv", "term_data.csv"):
            assert (term_dir / file_name).exists(), f"missing terminology file: {file_name}"


@pytest.mark.type4_knowledge
def test_import_package_structure(import_package_path: Path) -> None:
    """import_package 目录若存在，manifest.json 必须存在。

    import_package/ 整个目录不存在时跳过（尚未生成导入包）。
    manifest 中列出的文件才是本次实际要导入的内容，子目录按需存在即可。
    """
    if not import_package_path.exists():
        pytest.skip("import_package/ 目录不存在，请先运行 _gen_import_package.py，跳过")

    assert (import_package_path / "manifest.json").exists(), "manifest.json 缺失"


# ════════════════════════════════════════════════════════════════════════════
# 2. 知识包预检 API（api-unit，不写库）
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.type4_knowledge
def test_precheck_passes(knowledge_client, import_package_path: Path) -> None:
    """对 sales_analysis_demo import_package 调用预检接口，期望全部通过。"""
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
    # 每个文件摘要应有 file / rows 字段
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
    # 先清除旧数据
    notify_client.delete("/api/v1/knowledge/ingest/notify/latest")

    payload = {
        "status": "success",
        "folder_path": "/data/test_package",
        "stats": {
            "domains":   {"inserted": 2, "updated": 0, "deleted": 0},
            "libraries": {"inserted": 3, "updated": 0, "deleted": 0},
            "terms":     {"inserted": 50, "updated": 0, "deleted": 0},
            "relations": {"inserted": 52, "updated": 0, "deleted": 0},
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
# 4. 完整导入 + 回调集成测试（需真实数据库 + notify 服务运行）
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.type4_knowledge
@pytest.mark.integration
def test_run_with_callback(
    db_ready,                        # 确保 DDL + 内置术语类型 seed 已执行
    knowledge_client,
    notify_client,
    import_package_path: Path,
    integration_enabled: bool,
) -> None:
    """完整流程：预检 → 入库 → 回调通知。

    需要：
      - 真实 PostgreSQL/OpenGauss 数据库（环境变量 DATACLOUD_DB_URL 等配置正确）
      - DATACLOUD_ENABLE_INTEGRATION_TESTS=1
    db_ready fixture 会自动执行 apply_ddl() + apply_seed()，
    确保表结构和内置术语类型（ONTOLOGY_OBJ / ONTOLOGY_VIEW 等）已存在。
    """
    if not integration_enabled:
        pytest.skip("integration tests disabled (set DATACLOUD_ENABLE_INTEGRATION_TESTS=1)")

    # 先清除通知
    notify_client.delete("/api/v1/knowledge/ingest/notify/latest")

    # mock_env 服务在 TestClient 内，无法直接提供 HTTP 回调地址
    # 集成测试时需要服务真实运行，此处验证无回调的纯导入流程
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
    # 验证各实体均有写入（inserted + updated > 0，兼容重复导入场景）
    stats = body.get("stats", {})

    def _touched(entity: str) -> int:
        s = stats.get(entity, {})
        return s.get("inserted", 0) + s.get("updated", 0)

    assert _touched("domains") > 0, f"domains 无写入: {stats.get('domains')}"
    assert _touched("terms") > 0, f"terms 无写入: {stats.get('terms')}"
    assert _touched("relations") > 0, f"relations 无写入: {stats.get('relations')}"
    assert _touched("knowledge") > 0, f"knowledge 无写入: {stats.get('knowledge')}"

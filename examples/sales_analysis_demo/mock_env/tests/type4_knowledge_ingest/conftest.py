"""type4_knowledge_ingest 测试专用 fixture。

提供两个 TestClient：
  knowledge_client — 基于 knowledge_build 路由的最小 FastAPI 应用
  notify_client    — mock_env 完整 FastAPI 应用（含 knowledge/ingest/notify 端点）

db_ready fixture（集成测试前置条件检查）：
  验证数据库已就绪（表存在 + 内置术语类型已 seed），条件不满足则 skip。
  数据库初始化由运维/开发手动执行一次，测试只做检查，不修改数据库状态。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── 把 knowledge_build 模块所在目录加入 sys.path ──────────────────────────────
# packages/datacloud-knowledge/src/datacloud-knowledge/
_REPO_ROOT = Path(__file__).resolve().parents[5]   # repo root

_KB_SRC = (
    _REPO_ROOT
    / "packages"
    / "datacloud-knowledge"
    / "src"
    / "datacloud-knowledge"
)
if str(_KB_SRC) not in sys.path:
    sys.path.insert(0, str(_KB_SRC))



@pytest.fixture(scope="session")
def knowledge_client():
    """返回挂载了 knowledge_build 路由的 TestClient。

    不需要真实数据库；precheck 测试完全在内存中运行。
    """
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from knowledge_build.router import router as kb_router

    app = FastAPI(title="knowledge-build-test")
    app.include_router(kb_router)

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def notify_client():
    """返回 mock_env 完整应用的 TestClient（含 knowledge 通知接口）。"""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")

    from fastapi.testclient import TestClient
    from sales_analysis_demo.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def import_package_path(mock_env_root: Path) -> Path:
    """返回 sales_analysis_demo import_package 目录路径。"""
    return mock_env_root / "resource" / "knowledge" / "import_package"


@pytest.fixture(scope="session")
def db_ready(integration_enabled: bool) -> None:
    """集成测试前置条件检查：验证数据库已就绪，而不是负责初始化数据库。

    检查项：
      1. 能连上数据库（env 变量 DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME）
      2. whale_datacloud.term_type 表存在
      3. 内置术语类型（is_builtin=TRUE）至少有一条记录

    如果检查不通过，直接 skip 并输出修复指引，而不是自动修改数据库。

    初始化方式（一次性，由运维/开发手动执行）：
      cd packages/datacloud-knowledge
      python db/scripts/apply_whale_datacloud.py
    这会执行 DDL 建表 + seed 写入内置术语类型。

    跳过条件：
      未设置 DATACLOUD_ENABLE_INTEGRATION_TESTS=1 时自动跳过。
    """
    if not integration_enabled:
        pytest.skip("integration tests disabled (set DATACLOUD_ENABLE_INTEGRATION_TESTS=1)")

    import os
    import psycopg2  # type: ignore[import]

    # ── 检查环境变量 ─────────────────────────────────────────────────────────
    missing = [v for v in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")
               if not os.getenv(v)]
    if missing:
        pytest.skip(
            f"缺少数据库环境变量 {missing}，请配置后重试。\n"
            "提示：在 .vscode/.env.test 或环境中设置 DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME"
        )

    # ── 检查能否连接 ──────────────────────────────────────────────────────────
    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ["DB_PORT"]),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            dbname=os.environ["DB_NAME"],
        )
    except Exception as exc:
        pytest.skip(
            f"无法连接数据库: {exc}\n"
            "提示：请确认数据库服务已启动，环境变量配置正确。"
        )

    # ── 检查表存在 + 内置类型已 seed ─────────────────────────────────────────
    try:
        with conn.cursor() as cur:
            # 检查 term_type 表是否存在
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'whale_datacloud'
                  AND table_name   = 'term_type'
            """)
            if cur.fetchone()[0] == 0:
                pytest.skip(
                    "whale_datacloud.term_type 表不存在，请先执行 DDL 初始化：\n"
                    "  cd packages/datacloud-knowledge\n"
                    "  python db/scripts/apply_whale_datacloud.py"
                )

            # 检查所有必需的内置术语类型是否已 seed
            required_builtins = {
                "EMPLOYEE",
                "GENERAL",
                "ONTOLOGY_VIEW",
                "ONTOLOGY_OBJ",
                "ONTOLOGY_ACTION",
                "ONTOLOGY_FUNC",
                "ONTOLOGY_PARAM",
                "ONTOLOGY_PROP",
            }
            cur.execute(
                "SELECT type_code FROM whale_datacloud.term_type WHERE is_builtin = TRUE"
            )
            existing = {row[0] for row in cur.fetchall()}
            missing_types = required_builtins - existing
            if missing_types:
                pytest.skip(
                    f"以下内置术语类型尚未写入数据库：{sorted(missing_types)}\n"
                    "请执行 seed（幂等，不 drop 表）：\n"
                    "  cd packages/datacloud-knowledge\n"
                    "  python db/scripts/apply_whale_datacloud.py --seed-only"
                )
    finally:
        conn.close()

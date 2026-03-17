from pathlib import Path

import pytest
from dotenv import load_dotenv


# 在 pytest 进程启动时优先加载 mock_env/src/sales_analysis_demo/.env
_env_path = (
    Path(__file__)
    .resolve()
    .parents[2]  # .../mock_env
    / "src"
    / "sales_analysis_demo"
    / ".env"
)
if _env_path.exists():
    # 使用 override=True 覆盖上层（例如 mock_env/.env）里的同名变量
    load_dotenv(_env_path, override=True)


@pytest.fixture(scope="session")
def api_client():
    """在整个测试会话中复用同一个 TestClient，避免 event loop 不一致问题。"""
    from fastapi.testclient import TestClient
    from sales_analysis_demo.main import app

    with TestClient(app) as client:
        yield client


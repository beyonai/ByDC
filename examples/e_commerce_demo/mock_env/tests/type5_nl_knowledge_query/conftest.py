"""type5_nl_knowledge_query 测试专用 fixture。

提供自然语言查询测试所需的 fixture 和配置。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


# ── 把 datacloud_knowledge 包所在目录加入 sys.path ────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[5]  # repo root

_KB_SRC = _REPO_ROOT / "packages" / "datacloud-knowledge" / "src"
if str(_KB_SRC) not in sys.path:
    sys.path.insert(0, str(_KB_SRC))


@pytest.fixture(scope="session")
def mock_env_root() -> Path:
    """返回 mock_env 根目录路径。"""
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session")
def knowledge_service():
    """返回 SQLKnowledgeGraphQuery 服务实例。

    需要配置环境变量才能连接数据库：
    - DATACLOUD_DB_URL: 数据库 JDBC/URI 地址
    - DATACLOUD_DB_USER: 数据库用户名
    - DATACLOUD_DB_PASSWORD: 数据库密码
    """
    from dotenv import load_dotenv

    # 尝试加载环境变量
    env_paths = [
        mock_env_root() / ".env.example",
        _REPO_ROOT / ".vscode" / ".env.test",
        _REPO_ROOT / ".env",
    ]

    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path, override=True)
            break

    # 检查必要的环境变量
    required_vars = ["DATACLOUD_DB_URL", "DATACLOUD_DB_USER"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        pytest.skip(f"缺少数据库环境变量: {missing}")

    # 导入并创建服务
    try:
        from datacloud_knowledge import SQLKnowledgeGraphQuery

        service = SQLKnowledgeGraphQuery(default_hops=4)
        return service
    except Exception as exc:
        pytest.skip(f"无法初始化知识图谱服务: {exc}")


@pytest.fixture(scope="session")
def integration_enabled() -> bool:
    """检查是否启用了集成测试。"""
    return os.getenv("DATACLOUD_ENABLE_INTEGRATION_TESTS", "0") == "1"

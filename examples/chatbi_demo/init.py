"""chatbi_demo 初始化脚本。

从 .demo_env 读取环境变量，将 SQL 文件和 OWL 数据源文件中的占位符替换为实际值，
然后通过 psycopg 执行 SQL 完成数据库初始化。

用法：
    cd examples/chatbi_demo
    uv run python init.py
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DEMO_ROOT = Path(__file__).parent
_ENV_FILE = _DEMO_ROOT / ".demo_env"
_SQL_DIR = _DEMO_ROOT / "data/sql"
_RESOURCE_DIR = _DEMO_ROOT / "resource"

_OWL_FILES = [
    _RESOURCE_DIR / "object/by_customer/by_customer_dbsource.owl",
    _RESOURCE_DIR / "object/by_opp_task/by_opp_task_dbsource.owl",
    _RESOURCE_DIR / "object/by_opportunity/by_opportunity_dbsource.owl",
    _RESOURCE_DIR / "object/by_project/by_project_dbsource.owl",
    _RESOURCE_DIR / "object/by_project_task/by_project_task_dbsource.owl",
    _RESOURCE_DIR / "object/by_rd_task/by_rd_task_dbsource.owl",
    _RESOURCE_DIR / "object/po_organization/po_organization_dbsource.owl",
    _RESOURCE_DIR / "object/po_users/po_users_dbsource.owl",
]

_SQL_FILES = [
    _SQL_DIR / "01-crm_demo.sql",
    _SQL_DIR / "02-term.sql",
]


def _load_env(env_file: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def _render(template: str, env: dict[str, str]) -> str:
    def _replace(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in env:
            raise KeyError(f"占位符 {{{{{key}}}}} 在 .demo_env 中未定义")
        return env[key]

    return re.sub(r"\{\{(\w+)\}\}", _replace, template)


def _render_file(path: Path, env: dict[str, str]) -> str:
    # utf-8-sig 自动去除 UTF-8 BOM（Windows 工具生成的 SQL 文件常带 BOM）
    return _render(path.read_text(encoding="utf-8-sig"), env)


def _execute_sql(sql_content: str, env: dict[str, str]) -> None:
    try:
        import psycopg
    except ImportError:
        logger.error("psycopg 未安装，请先执行: uv add psycopg")
        sys.exit(1)

    host = env["DATACLOUD_DB_HOST"]
    port = int(env.get("DATACLOUD_DB_PORT", "5432"))
    database = env.get("DATACLOUD_DB_DATABASE", "postgres")
    user = env["DATACLOUD_DB_USER"]
    password = env["DATACLOUD_DB_PASSWORD"]
    schema = env["DATACLOUD_DB_SCHEMA"]

    conninfo = (
        f"host={host} port={port} dbname={database} "
        f"user={user} password={password}"
    )
    with psycopg.connect(conninfo, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SET search_path TO {schema}")  # noqa: S608
            for stmt in sql_content.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
        conn.commit()


def main() -> None:
    if not _ENV_FILE.exists():
        logger.error(".demo_env 不存在: %s", _ENV_FILE)
        sys.exit(1)

    env = _load_env(_ENV_FILE)
    logger.info(
        "已加载配置: host=%s port=%s database=%s schema=%s user=%s",
        env.get("DATACLOUD_DB_HOST"),
        env.get("DATACLOUD_DB_PORT"),
        env.get("DATACLOUD_DB_DATABASE"),
        env.get("DATACLOUD_DB_SCHEMA"),
        env.get("DATACLOUD_DB_USER"),
    )

    # 渲染并写回 OWL 文件（用实际值替换占位符后写入磁盘）
    logger.info("── 渲染 OWL 数据源文件 ──")
    for owl_path in _OWL_FILES:
        rendered = _render_file(owl_path, env)
        owl_path.write_text(rendered, encoding="utf-8")
        logger.info("  OK %s", owl_path.name)

    # 渲染 SQL 并执行
    logger.info("── 执行 SQL 初始化 ──")
    for sql_path in _SQL_FILES:
        logger.info("  执行: %s", sql_path.name)
        sql_content = _render_file(sql_path, env)
        _execute_sql(sql_content, env)
        logger.info("  OK %s 完成", sql_path.name)

    logger.info("初始化完成")


if __name__ == "__main__":
    main()

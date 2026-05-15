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

_OWL_TEMPLATES = [
    _RESOURCE_DIR / "object/by_customer/by_customer_dbsource.owl.template",
    _RESOURCE_DIR / "object/by_opp_task/by_opp_task_dbsource.owl.template",
    _RESOURCE_DIR / "object/by_opportunity/by_opportunity_dbsource.owl.template",
    _RESOURCE_DIR / "object/by_project/by_project_dbsource.owl.template",
    _RESOURCE_DIR / "object/by_project_task/by_project_task_dbsource.owl.template",
    _RESOURCE_DIR / "object/by_rd_task/by_rd_task_dbsource.owl.template",
    _RESOURCE_DIR / "object/po_organization/po_organization_dbsource.owl.template",
    _RESOURCE_DIR / "object/po_users/po_users_dbsource.owl.template",
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


def _render_file(path: Path, env: dict[str, str], encoding: str = "utf-8") -> str:
    content = path.read_text(encoding=encoding)
    # 修正 DBeaver 导出的双点语法：
    #   "schema".."table"  → "schema"."table"  （标识符）
    #   "schema"..seq_name → "schema".seq_name  （nextval 字符串内）
    content = content.replace('".."', '"."')
    content = re.sub(r'("[\w]+")\.\.([\w]+)', r'\1.\2', content)
    return _render(content, env)


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
    ddl_stmts, dml_stmts = _split_sql_ddl_dml(sql_content)
    logger.info("    DDL 语句数=%d  DML 语句数=%d", len(ddl_stmts), len(dml_stmts))

    # 从 DDL 中提取所有被 nextval 引用的序列名，提前创建（导出时可能漏掉 CREATE SEQUENCE）
    # nextval('"schema".seq_name'::regclass) 格式
    seq_names = sorted({
        m.group(1)
        for stmt in ddl_stmts
        for m in re.finditer(r"nextval\('[^']*?\.?([\w]+)'", stmt)
    })

    with psycopg.connect(conninfo, autocommit=True, client_encoding="utf-8") as conn:
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')  # noqa: S608
        conn.execute(f'SET search_path TO "{schema}"')  # noqa: S608
        # 先确保序列存在（幂等）
        for seq in seq_names:
            logger.info("    CREATE SEQUENCE IF NOT EXISTS %s", seq)
            conn.execute(f'CREATE SEQUENCE IF NOT EXISTS "{seq}"')  # noqa: S608
        # 再执行 DDL（建表），跳过依赖缺失函数的 TRIGGER，最后执行 DML（插入数据）
        for stmt in ddl_stmts:
            upper = stmt.lstrip().upper()
            if upper.startswith("CREATE TRIGGER"):
                logger.info("    跳过 TRIGGER: %s", stmt[:60].replace("\n", " "))
                continue
            # 跳过依赖 pgvector 扩展的向量索引
            if "vector_cosine_ops" in stmt or "vector_l2_ops" in stmt or "vector_ip_ops" in stmt:
                logger.info("    跳过向量索引(需要pgvector): %s", stmt[:60].replace("\n", " "))
                continue
            try:
                conn.execute(stmt)
            except Exception as exc:
                logger.error("DDL 执行失败: %s\n语句: %s", exc, stmt[:200])
                raise
        for stmt in dml_stmts:
            conn.execute(stmt)


def _split_sql_ddl_dml(sql: str) -> tuple[list[str], list[str]]:
    """按分号拆分 SQL，分别返回 DDL 和 DML 语句列表。"""
    ddl: list[str] = []
    dml: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt:
                upper = stmt.lstrip().upper()
                if upper.startswith("INSERT"):
                    dml.append(stmt)
                else:
                    ddl.append(stmt)
            buf = []
    remainder = "\n".join(buf).strip().rstrip(";").strip()
    if remainder:
        upper = remainder.lstrip().upper()
        if upper.startswith("INSERT"):
            dml.append(remainder)
        else:
            ddl.append(remainder)
    return ddl, dml


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

    # 渲染 OWL 模板，写到同名 .owl 文件（模板保持占位符不变）
    logger.info("── 渲染 OWL 数据源文件 ──")
    for tmpl_path in _OWL_TEMPLATES:
        rendered = _render_file(tmpl_path, env)
        owl_path = tmpl_path.with_suffix("")  # 去掉 .template 后缀
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

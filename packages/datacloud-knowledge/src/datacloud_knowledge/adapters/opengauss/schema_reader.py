"""OpenGauss Schema Reader Adapter — 读取 OpenGauss 表结构供 OWL 生成器使用。

替代原有 schema_reader.py（硬编码 pymysql 直连 MySQL），
通过 adapters 层的连接管理统一访问 OpenGauss/PostgreSQL。
遵循 AGENTS.md 分层约束：非 adapter 代码不得直接 import psycopg。

职责：
- 查询 INFORMATION_SCHEMA.COLUMNS 获取表结构
- 查询 DISTINCT 值获取术语化字段的枚举数据
- 返回与现有 Table/Column 数据模型兼容的输出

用法:
    from datacloud_knowledge.adapters.opengauss.schema_reader import read_tables
    tables = read_tables(schema="demo", table_codes=["by_customer"], ...)
"""

from __future__ import annotations

import logging
from collections import OrderedDict

import psycopg
from psycopg import sql as psql

from datacloud_knowledge.adapters.opengauss._db.url import build_postgres_connection_uri
from datacloud_knowledge.ingestion.owl_generate.models import Column, OwlGenConfig, Table

logger = logging.getLogger(__name__)


def read_tables(
    schema: str,
    table_codes: list[str],
    *,
    table_names: dict[str, str] | None = None,
    table_descs: dict[str, str] | None = None,
    host: str = "",
    port: int = 5432,
    database: str = "",
    user: str = "",
    password: str = "",
    db_url: str = "",
    conninfo: str = "",
) -> list[Table]:
    """从 OpenGauss INFORMATION_SCHEMA.COLUMNS 读取表结构。

    Args:
        schema: 目标 schema 名称（如 "demo"）。
        table_codes: 要读取的表编码列表（表名）。
        table_names: 表编码 → 中文名映射（可选）。
        table_descs: 表编码 → 描述映射（可选）。
        host: 主机地址。也可通过 db_url/conninfo 指定。
        port: 端口，默认 5432。
        database: 数据库名。
        user: 用户名。
        password: 密码。
        db_url: JDBC 风格 DB URL（如 "jdbc:opengauss://host:5432/db"）。
        conninfo: libpq 连接字符串（psycopg 原生格式）。

    Returns:
        Table 列表，与 MySQL schema_reader 输出格式一致。
    """
    _names = table_names or {}
    _descs = table_descs or {}

    uri = _resolve_connection_uri(
        schema=schema,
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        db_url=db_url,
        conninfo=conninfo,
    )

    tables: list[Table] = []
    try:
        with psycopg.connect(conninfo=uri) as conn, conn.cursor() as cur:
            # 设置 search_path 实现 schema 隔离
            # 注意：SET 命令不支持参数化占位符，必须使用 psycopg.sql 构建
            cur.execute(psql.SQL("SET search_path TO {}, public").format(psql.Identifier(schema)))

            for table_code in table_codes:
                # 查询 INFORMATION_SCHEMA.COLUMNS 获取表结构
                cur.execute(
                    """
                        SELECT
                            COLUMN_NAME,
                            COALESCE(UDT_NAME, DATA_TYPE) AS COLUMN_TYPE,
                            CASE WHEN IS_NULLABLE = 'YES' THEN TRUE ELSE FALSE END AS IS_NULLABLE,
                            COALESCE(
                                pg_catalog.col_description(
                                    (SELECT c.oid FROM pg_catalog.pg_class c
                                     JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                                     WHERE c.relname = %s AND n.nspname = %s),
                                    ORDINAL_POSITION
                                ),
                                ''
                            ) AS COLUMN_COMMENT,
                            CASE
                                WHEN COLUMN_NAME IN (
                                    SELECT kcu.COLUMN_NAME
                                    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                                    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                                        ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                                        AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
                                    WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                                        AND tc.TABLE_SCHEMA = %s
                                        AND tc.TABLE_NAME = %s
                                ) THEN TRUE
                                ELSE FALSE
                            END AS IS_PRIMARY_KEY
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_SCHEMA = %s
                            AND TABLE_NAME = %s
                        ORDER BY ORDINAL_POSITION
                        """,
                    (table_code, schema, schema, table_code, schema, table_code),
                )
                rows = cur.fetchall()

                columns: list[Column] = []
                primary_keys: list[str] = []
                for row in rows:
                    col = Column(
                        name=str(row[0]),
                        sql_type=str(row[1]),
                        nullable=bool(row[2]),
                        comment=str(row[3] or ""),
                        is_primary_key=bool(row[4]),
                    )
                    columns.append(col)
                    if col.is_primary_key:
                        primary_keys.append(col.name)

                if columns:
                    tables.append(
                        Table(
                            code=table_code,
                            name=_names.get(table_code, table_code),
                            desc=_descs.get(table_code, ""),
                            columns=columns,
                            primary_keys=primary_keys,
                        )
                    )
                else:
                    logger.warning("表 '%s.%s' 不存在或无字段", schema, table_code)

    except psycopg.Error:
        logger.exception("OpenGauss schema 读取失败")
        raise

    logger.info(
        "读取 %d 张表结构（共 %d 字段）from schema=%s",
        len(tables),
        sum(len(t.columns) for t in tables),
        schema,
    )
    return tables


def load_term_values(
    schema: str,
    table_code: str,
    column_name: str,
    *,
    host: str = "",
    port: int = 5432,
    database: str = "",
    user: str = "",
    password: str = "",
    db_url: str = "",
    conninfo: str = "",
) -> list[str]:
    """从 OpenGauss 表读取指定字段的 DISTINCT 值。

    用于获取术语化字段的所有枚举值（如商机状态的 "签约成功"、"进行中" 等）。

    Args:
        schema: 目标 schema。
        table_code: 表名。
        column_name: 字段名。
        host/port/database/user/password/db_url/conninfo: 连接参数。

    Returns:
        DISTINCT 值列表，已去重并排序。
    """
    uri = _resolve_connection_uri(
        schema=schema,
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        db_url=db_url,
        conninfo=conninfo,
    )

    values: list[str] = []
    try:
        with psycopg.connect(conninfo=uri) as conn, conn.cursor() as cur:
            cur.execute(psql.SQL("SET search_path TO {}, public").format(psql.Identifier(schema)))
            # 使用标识符引用避免 SQL 注入
            # 注意：OpenGauss 中 column != '' 对 character 类型始终返回 NULL，
            # 必须用 LENGTH(column) > 0 替代。
            cur.execute(
                psql.SQL(
                    "SELECT DISTINCT {col} FROM {schema}.{table}"
                    " WHERE {col} IS NOT NULL AND LENGTH({col}) > 0 ORDER BY {col}"
                ).format(
                    col=psql.Identifier(column_name),
                    schema=psql.Identifier(schema),
                    table=psql.Identifier(table_code),
                )
            )
            values = [str(row[0]).strip() for row in cur.fetchall() if row[0] is not None]
    except psycopg.Error:
        logger.exception(
            "读取 DISTINCT 值失败: %s.%s.%s",
            schema,
            table_code,
            column_name,
        )
        raise

    return values


def load_all_term_values(
    config: OwlGenConfig,
) -> dict[str, list[dict[str, str]]]:
    """从配置读取所有术语化字段的 DISTINCT 值（兼容原有接口）。

    返回与 MySQL schema_reader.load_term_values() 相同格式的数据。

    Args:
        config: OwlGenConfig 配置。

    Returns:
        {term_type_code: [{code, name, parent_prop_code}, ...]} 字典。
    """
    schema = config.db_params.get("schema", "")
    if not schema:
        schema = config.db_params.get("database", config.mysql_database)

    host = config.db_params.get("host", config.mysql_host)
    port = config.db_params.get("port", config.mysql_port)
    database = config.db_params.get("database", config.mysql_database)
    user = config.db_params.get("user", config.mysql_user)
    password = config.db_params.get("password", config.mysql_password)

    term_values: dict[str, OrderedDict[str, str]] = {}
    type_parent_map: dict[str, str] = {}

    for binding in config.term_bindings:
        term_values.setdefault(binding.term_type_code, OrderedDict())
        type_parent_map.setdefault(
            binding.term_type_code,
            config.resolve_object_prop_code(binding.table_code, binding.column_name),
        )

        try:
            distinct_values = load_term_values(
                schema=schema,
                table_code=binding.table_code,
                column_name=binding.column_name,
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
            )
            for val in distinct_values:
                if val:
                    term_values[binding.term_type_code].setdefault(val, val)
        except Exception:
            logger.warning(
                "跳过术语值读取: %s.%s.%s",
                schema,
                binding.table_code,
                binding.column_name,
                exc_info=True,
            )

    return {
        type_code: [
            {
                "code": code,
                "name": name,
                "parent_prop_code": type_parent_map.get(type_code, ""),
            }
            for code, name in values.items()
        ]
        for type_code, values in term_values.items()
        if values
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_connection_uri(
    schema: str,
    host: str = "",
    port: int = 5432,
    database: str = "",
    user: str = "",
    password: str = "",
    db_url: str = "",
    conninfo: str = "",
) -> str:
    """根据参数解析连接 URI。优先级：conninfo > db_url > 环境变量。"""
    if conninfo:
        return conninfo

    if db_url:
        return build_postgres_connection_uri(schema=schema, db_url=db_url)

    if host and database:
        # 手动构建 JDBC 风格 URL，复用 build_postgres_connection_uri
        constructed_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        return build_postgres_connection_uri(schema=schema, db_url=constructed_url)

    # 回退到环境变量
    return build_postgres_connection_uri(schema=schema, db_url=None)


__all__ = [
    "load_all_term_values",
    "load_term_values",
    "read_tables",
]

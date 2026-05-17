"""数据库 schema 读取器 — 统一 MySQL/OpenGauss 表结构读取。

通过 adapter 工厂模式支持多种数据库后端：
- MySQL: 直接 pymysql 连接（旧路径，逐步迁移）。
- OpenGauss / PostgreSQL: 委托 adapters/opengauss/schema_reader.py。

生成器调用方不直接 import 数据库驱动，全部通过此模块。
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from importlib import import_module
from typing import Any

from datacloud_knowledge.ingestion.owl_generate.models import Column, OwlGenConfig, Table

logger = logging.getLogger(__name__)


def _db_backend(config: OwlGenConfig) -> str:
    """推断数据库后端类型：优先 db_type，否则从 db_params/driver 推断。"""
    db_type = config.db_type.lower()
    if db_type in ("opengauss", "postgresql", "postgres"):
        return "opengauss"
    if db_type == "mysql":
        return "mysql"
    # 从 db_params 推断
    db_params_type = str(config.db_params.get("db_type", "")).lower()
    if db_params_type in ("opengauss", "postgresql", "postgres"):
        return "opengauss"
    if db_params_type == "mysql":
        return "mysql"
    # 默认：如果 config 中有 mysql_host，用 MySQL；否则用 opengauss
    if config.mysql_host:
        return "mysql"
    return "opengauss"


def read_tables(config: OwlGenConfig) -> list[Table]:
    """从数据库 INFORMATION_SCHEMA 读取表结构（自动选择 MySQL/OpenGauss 后端）。"""
    backend = _db_backend(config)

    if backend == "opengauss":
        return _read_tables_opengauss(config)

    return _read_tables_mysql(config)


def load_term_values(
    config: OwlGenConfig,
) -> dict[str, list[dict[str, str]]]:
    """从数据库读取术语化字段的 DISTINCT 值（自动选择后端）。

    返回 ``{term_type_code: [{code, name, parent_prop_code}, ...]}``。
    """
    backend = _db_backend(config)

    if backend == "opengauss":
        return _load_term_values_opengauss(config)

    return _load_term_values_mysql(config)


# ═══════════════════════════════════════════════════════════════════════════════
# OpenGauss / PostgreSQL 后端（通过 adapters 层）
# ═══════════════════════════════════════════════════════════════════════════════


def _read_tables_opengauss(config: OwlGenConfig) -> list[Table]:
    """通过 adapters/opengauss/schema_reader.py 读取 OpenGauss 表结构。"""
    from datacloud_knowledge.adapters.opengauss.schema_reader import (
        read_tables as og_read_tables,
    )

    schema = config.db_params.get("schema", "") or config.db_params.get(
        "database", config.mysql_database
    )
    if not schema:
        schema = config.mysql_database

    return og_read_tables(
        schema=schema,
        table_codes=config.table_codes,
        table_names=config.table_names,
        table_descs=config.table_descs,
        host=config.db_params.get("host", config.mysql_host),
        port=config.db_params.get("port", config.mysql_port) or 5432,
        database=config.db_params.get("database", config.mysql_database),
        user=config.db_params.get("user", config.mysql_user),
        password=config.db_params.get("password", config.mysql_password),
    )


def _load_term_values_opengauss(
    config: OwlGenConfig,
) -> dict[str, list[dict[str, str]]]:
    """通过 adapters/opengauss/schema_reader.py 读取 OpenGauss 术语值。"""
    from datacloud_knowledge.adapters.opengauss.schema_reader import (
        load_all_term_values,
    )

    return load_all_term_values(config)


# ═══════════════════════════════════════════════════════════════════════════════
# MySQL 后端（旧路径，保留作为兼容）
# ═══════════════════════════════════════════════════════════════════════════════


def _load_pymysql() -> Any:
    """延迟加载 pymysql，避免类型检查依赖外部 stub。"""
    return import_module("pymysql")


def _read_tables_mysql(config: OwlGenConfig) -> list[Table]:
    """从 MySQL INFORMATION_SCHEMA 读取表结构。"""
    pymysql = _load_pymysql()

    conn = pymysql.connect(
        host=config.mysql_host,
        port=config.mysql_port,
        user=config.mysql_user,
        password=config.mysql_password,
        database=config.mysql_database,
        charset="utf8mb4",
    )
    tables: list[Table] = []
    try:
        with conn.cursor() as cur:
            for table_code in config.table_codes:
                cur.execute(
                    """
                    SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
                           COLUMN_COMMENT, COLUMN_KEY
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (config.mysql_database, table_code),
                )
                columns: list[Column] = []
                primary_keys: list[str] = []
                for row in cur.fetchall():
                    col = Column(
                        name=row[0],
                        sql_type=row[1],
                        nullable=row[2] == "YES",
                        comment=row[3] or "",
                        is_primary_key=row[4] == "PRI",
                    )
                    columns.append(col)
                    if col.is_primary_key:
                        primary_keys.append(col.name)

                tables.append(
                    Table(
                        code=table_code,
                        name=config.table_names.get(table_code, table_code),
                        desc=config.table_descs.get(table_code, ""),
                        columns=columns,
                        primary_keys=primary_keys,
                    )
                )
    finally:
        conn.close()

    return tables


def _load_term_values_mysql(
    config: OwlGenConfig,
) -> dict[str, list[dict[str, str]]]:
    """从 MySQL 读取术语化字段的 DISTINCT 值。"""
    pymysql = _load_pymysql()

    conn = pymysql.connect(
        host=config.mysql_host,
        port=config.mysql_port,
        user=config.mysql_user,
        password=config.mysql_password,
        database=config.mysql_database,
        charset="utf8mb4",
    )
    # 按 term_type_code 分组，OrderedDict 去重，并保留父属性编码。
    term_values: dict[str, OrderedDict[str, str]] = {}
    type_parent_map: dict[str, str] = {}
    for binding in config.term_bindings:
        term_values.setdefault(binding.term_type_code, OrderedDict())
        type_parent_map.setdefault(
            binding.term_type_code,
            config.resolve_object_prop_code(binding.table_code, binding.column_name),
        )

    try:
        with conn.cursor() as cur:
            for binding in config.term_bindings:
                cur.execute(
                    f"SELECT DISTINCT `{binding.column_name}` "
                    f"FROM `{binding.table_code}` "
                    f"WHERE `{binding.column_name}` IS NOT NULL "
                    f"AND `{binding.column_name}` != '' "
                    f"ORDER BY `{binding.column_name}`"
                )
                for (value,) in cur.fetchall():
                    val = str(value).strip()
                    if val:
                        term_values[binding.term_type_code].setdefault(val, val)
    finally:
        conn.close()

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

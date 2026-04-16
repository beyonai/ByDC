"""MySQL schema 读取器。

职责：连接 MySQL，读取 INFORMATION_SCHEMA 表结构 + 术语化字段的 DISTINCT 值。
与 OWL 渲染完全解耦，只返回数据模型。
"""

from __future__ import annotations

from collections import OrderedDict

from datacloud_knowledge.owl_gen.models import Column, OwlGenConfig, Table


def read_tables(config: OwlGenConfig) -> list[Table]:
    """从 MySQL INFORMATION_SCHEMA 读取表结构。"""
    import pymysql  # type: ignore[import-untyped]

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


def load_term_values(
    config: OwlGenConfig,
) -> dict[str, list[dict[str, str]]]:
    """从 MySQL 读取术语化字段的 DISTINCT 值。

    返回 ``{term_type_code: [{code, name}, ...]}``。
    """
    import pymysql

    conn = pymysql.connect(
        host=config.mysql_host,
        port=config.mysql_port,
        user=config.mysql_user,
        password=config.mysql_password,
        database=config.mysql_database,
        charset="utf8mb4",
    )
    # 按 term_type_code 分组，OrderedDict 去重
    term_values: dict[str, OrderedDict[str, str]] = {}
    for binding in config.term_bindings:
        term_values.setdefault(binding.term_type_code, OrderedDict())

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
        type_code: [{"code": code, "name": name} for code, name in values.items()]
        for type_code, values in term_values.items()
        if values
    }

"""将 Base 中的 Datasource 实体转换为 OntologyLoader 运行时配置。"""

from __future__ import annotations

from typing import Any


def build_datasource_configs(
    entities: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    configs: dict[str, dict[str, Any]] = {}
    for entity in entities:
        for connection in entity.get("db", []) or []:
            alias = str(
                connection.get("dbId")
                or connection.get("db_id")
                or connection.get("dbCode")
                or connection.get("db_code")
                or ""
            )
            if not alias:
                continue
            params = connection.get("dbParams", connection.get("db_params")) or {}
            configs[alias] = {
                **params,
                "alias": alias,
                "db_type": str(
                    connection.get("dbType", connection.get("db_type", "SQLITE"))
                ),
            }
    return configs

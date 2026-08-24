"""Build a PostgreSQL/OpenGauss runtime Datasource from DATACLOUD_DB_* settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

from datacloud_platform.models.datasource import Datasource, DbConnection
from datacloud_platform.publishing import PublishContext


@dataclass(frozen=True, slots=True)
class EnterpriseDatabaseSettings:
    """Normalized PostgreSQL/OpenGauss connection settings for object instances."""

    host: str
    port: int
    database: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> EnterpriseDatabaseSettings:
        raw_port = os.getenv("DATACLOUD_DB_PORT", "5432").strip() or "5432"
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ValueError("DATACLOUD_DB_PORT 必须是有效整数") from exc
        if not 1 <= port <= 65535:
            raise ValueError("DATACLOUD_DB_PORT 必须在 1 到 65535 之间")
        return cls(
            host=os.getenv("DATACLOUD_DB_HOST", "localhost").strip() or "localhost",
            port=port,
            database=(
                os.getenv("DATACLOUD_DB_DATABASE", "postgres").strip() or "postgres"
            ),
            user=os.getenv("DATACLOUD_DB_USER", "postgres").strip() or "postgres",
            password=os.getenv("DATACLOUD_DB_PASSWORD", ""),
        )

    def to_datasource(self, context: PublishContext) -> Datasource:
        if context.db_type == "SQLITE":
            raise ValueError("数据库 Datasource 不接受 SQLite 发布上下文")
        if context.schema_name is None:
            raise ValueError("企业 Datasource 缺少租户 schema")
        scheme = context.db_type.lower()
        jdbc_url = (
            f"jdbc:{scheme}://{self.host}:{self.port}/{self.database}"
            f"?currentSchema={context.schema_name}"
        )
        return Datasource(
            db=[
                DbConnection(
                    dbId=context.datasource_alias,
                    dbCode=context.datasource_alias,
                    dbType=context.db_type,
                    dbParams={
                        "jdbc_url": jdbc_url,
                        "user": self.user,
                        "password": self.password,
                        "pool_min": 1,
                        "pool_max": 5,
                        "pool_timeout": 30,
                    },
                )
            ],
            ownerType=context.owner_type,
            userCode=context.user_code if context.owner_type == "personal" else None,
        )


def datasource_from_environment(context: PublishContext) -> Datasource:
    """Create the persisted Base Datasource for a PostgreSQL/OpenGauss publish."""

    return EnterpriseDatabaseSettings.from_env().to_datasource(context)

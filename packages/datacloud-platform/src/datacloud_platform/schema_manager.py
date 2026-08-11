"""个人与企业动态对象表 DDL 管理。"""

from __future__ import annotations

import re
from typing import Any, Protocol
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from datacloud_data_sdk.ddl import table_manager
from datacloud_knowledge.ingestion.workspace_manager import (
    FieldDiff,
    is_system_field_code,
)
from datacloud_platform.publishing import PublishContext

_IDENTIFIER_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,62}")
_TYPE_MAP: dict[str, str] = {
    "STRING": "TEXT",
    "INTEGER": "BIGINT",
    "FLOAT": "DOUBLE PRECISION",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "DATETIME": "TIMESTAMP",
    "TIMESTAMP": "TIMESTAMP",
}


class TargetTableConfirmationRequired(RuntimeError):
    """目标端同名表存在，需要显式确认删除重建。"""

    def __init__(self, qualified_table: str) -> None:
        super().__init__(f"目标表 {qualified_table} 已存在，需确认后删除并重建")
        self.qualified_table = qualified_table


class EnterpriseDatasourceConfigurationError(RuntimeError):
    """企业数据源定义缺失或与部署数据库类型不匹配。"""


class UnsupportedFieldTypeChange(RuntimeError):
    """动态表不自动执行字段类型变更。"""


class EnterpriseSqlExecutor(Protocol):
    def scalar(self, sql: str, params: dict[str, Any]) -> Any: ...

    def execute_transaction(
        self, statements: list[tuple[str, dict[str, Any]]]
    ) -> None: ...


class SqlAlchemyEnterpriseExecutor:
    """使用本体 Base 中已登记的数据源连接执行同步 DDL。"""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @classmethod
    def from_datasource(
        cls,
        context: PublishContext,
        datasource: dict[str, Any] | None,
    ) -> SqlAlchemyEnterpriseExecutor:
        if not datasource:
            raise EnterpriseDatasourceConfigurationError(
                f"Base {context.base_id} 未登记数据源 {context.datasource_alias}"
            )
        entry = next(
            (
                item
                for item in datasource.get("db", [])
                if item.get("dbId", item.get("db_id")) == context.datasource_alias
            ),
            None,
        )
        if entry is None:
            raise EnterpriseDatasourceConfigurationError(
                f"数据源中不存在连接 {context.datasource_alias}"
            )
        configured_type = str(entry.get("dbType", entry.get("db_type", ""))).upper()
        if configured_type != context.db_type:
            raise EnterpriseDatasourceConfigurationError(
                f"数据源类型 {configured_type or '<empty>'} 与部署类型 {context.db_type} 不一致"
            )
        params = entry.get("dbParams", entry.get("db_params")) or {}
        jdbc_url = str(params.get("jdbc_url", params.get("jdbcUrl", "")))
        if not jdbc_url:
            raise EnterpriseDatasourceConfigurationError(
                f"数据源 {context.datasource_alias} 缺少 dbParams.jdbc_url"
            )
        url = _sync_sqlalchemy_url(
            jdbc_url,
            context.db_type,
            str(params.get("user", "")),
            str(params.get("password", "")),
        )
        engine = create_engine(
            url,
            pool_size=int(params.get("pool_min", params.get("poolMin", 1))),
            max_overflow=max(
                0,
                int(params.get("pool_max", params.get("poolMax", 5)))
                - int(params.get("pool_min", params.get("poolMin", 1))),
            ),
            pool_timeout=float(
                params.get("pool_timeout", params.get("poolTimeout", 30))
            ),
        )
        return cls(engine)

    def scalar(self, sql: str, params: dict[str, Any]) -> Any:
        with self._engine.connect() as connection:
            return connection.execute(text(sql), params).scalar()

    def execute_transaction(self, statements: list[tuple[str, dict[str, Any]]]) -> None:
        with self._engine.begin() as connection:
            for sql, params in statements:
                connection.execute(text(sql), params)


class PersonalSqliteSchemaManager:
    """保持现有个人 SQLite 的增量 DDL 行为。"""

    schema_name: None = None

    @staticmethod
    def target_table_exists(entity_code: str) -> bool:
        _validate_identifier(entity_code)
        return table_manager.table_exists(entity_code)

    def create_or_recreate(
        self,
        entity_code: str,
        fields: list[dict[str, Any]],
        *,
        recreate: bool,
        confirm_drop_target_table: bool,
    ) -> None:
        _validate_fields(entity_code, fields)
        exists = self.target_table_exists(entity_code)
        if exists and recreate and not confirm_drop_target_table:
            raise TargetTableConfirmationRequired(entity_code)
        if exists and recreate:
            table_manager.drop_table(entity_code)
        if not exists or recreate:
            table_manager.create_table(entity_code, fields)

    @staticmethod
    def apply_incremental(
        entity_code: str,
        diff: FieldDiff,
        *,
        confirm_drop_columns: bool,
    ) -> None:
        _validate_identifier(entity_code)
        if diff.type_changed:
            raise UnsupportedFieldTypeChange(
                f"对象 {entity_code} 存在字段类型变更，需人工迁移后再发布"
            )
        if diff.added:
            table_manager.add_columns(entity_code, diff.added)
        removable_columns = [
            column for column in diff.removed if not is_system_field_code(column)
        ]
        if removable_columns and confirm_drop_columns:
            table_manager.drop_columns(entity_code, removable_columns)


class EnterpriseSqlSchemaManager:
    """在发布上下文指定的租户 schema 中管理 PostgreSQL/OpenGauss 表。"""

    def __init__(
        self, context: PublishContext, executor: EnterpriseSqlExecutor
    ) -> None:
        if context.owner_type != "enterprise" or not context.schema_name:
            raise ValueError("EnterpriseSqlSchemaManager 只接受企业发布上下文")
        _validate_identifier(context.schema_name)
        self._context = context
        self._executor = executor
        self.schema_name = context.schema_name

    def target_table_exists(self, entity_code: str) -> bool:
        _validate_identifier(entity_code)
        result = self._executor.scalar(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema_name AND table_name = :table_name)",
            {"schema_name": self.schema_name, "table_name": entity_code},
        )
        return bool(result)

    def create_or_recreate(
        self,
        entity_code: str,
        fields: list[dict[str, Any]],
        *,
        recreate: bool,
        confirm_drop_target_table: bool,
    ) -> None:
        _validate_fields(entity_code, fields)
        qualified = self._qualified(entity_code)
        exists = self.target_table_exists(entity_code)
        if exists and recreate and not confirm_drop_target_table:
            raise TargetTableConfirmationRequired(qualified)

        statements: list[tuple[str, dict[str, Any]]] = [
            (f'CREATE SCHEMA IF NOT EXISTS "{self.schema_name}"', {})
        ]
        if exists and recreate:
            statements.append((f"DROP TABLE IF EXISTS {qualified}", {}))
        if not exists or recreate:
            statements.append((self._create_table_sql(entity_code, fields), {}))
        self._executor.execute_transaction(statements)

    def apply_incremental(
        self,
        entity_code: str,
        diff: FieldDiff,
        *,
        confirm_drop_columns: bool,
    ) -> None:
        _validate_identifier(entity_code)
        if diff.type_changed:
            raise UnsupportedFieldTypeChange(
                f"对象 {entity_code} 存在字段类型变更，需人工迁移后再发布"
            )
        qualified = self._qualified(entity_code)
        statements: list[tuple[str, dict[str, Any]]] = []
        for field in diff.added:
            column = str(field.get("property_code", ""))
            _validate_identifier(column)
            sql_type = _field_sql_type(field)
            statements.append(
                (f'ALTER TABLE {qualified} ADD COLUMN "{column}" {sql_type}', {})
            )
        if confirm_drop_columns:
            for column in diff.removed:
                if is_system_field_code(column):
                    continue
                _validate_identifier(column)
                statements.append(
                    (f'ALTER TABLE {qualified} DROP COLUMN "{column}"', {})
                )
        if statements:
            self._executor.execute_transaction(statements)

    def _qualified(self, entity_code: str) -> str:
        return f'"{self.schema_name}"."{entity_code}"'

    def _create_table_sql(self, entity_code: str, fields: list[dict[str, Any]]) -> str:
        columns: list[str] = []
        for field in fields:
            column = str(field.get("property_code", ""))
            if column.lower() == "id" and field.get("is_primary_key"):
                columns.append(f'"{column}" BIGSERIAL PRIMARY KEY')
                continue
            definition = f'"{column}" {_field_sql_type(field)}'
            if field.get("is_required"):
                definition += " NOT NULL"
            if field.get("is_primary_key"):
                definition += " PRIMARY KEY"
            columns.append(definition)
        return f"CREATE TABLE {self._qualified(entity_code)} ({', '.join(columns)})"


def _validate_identifier(value: str) -> None:
    if not value.isascii() or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"非法 SQL 标识符: {value!r}")


def _validate_fields(entity_code: str, fields: list[dict[str, Any]]) -> None:
    _validate_identifier(entity_code)
    for field in fields:
        column = str(field.get("property_code", ""))
        _validate_identifier(column)
        _field_sql_type(field)


def _field_sql_type(field: dict[str, Any]) -> str:
    data_type = str(field.get("data_type", "STRING")).upper()
    try:
        return _TYPE_MAP[data_type]
    except KeyError as exc:
        raise ValueError(f"企业实例表不支持字段类型: {data_type}") from exc


def _sync_sqlalchemy_url(jdbc_url: str, db_type: str, user: str, password: str) -> str:
    raw = jdbc_url.removeprefix("jdbc:")
    parsed = urlparse(raw)
    scheme = "postgresql+psycopg2" if db_type == "POSTGRESQL" else "opengauss+psycopg2"
    netloc = parsed.netloc
    if user:
        credentials = quote_plus(user)
        if password:
            credentials += f":{quote_plus(password)}"
        host = parsed.hostname or ""
        if parsed.port:
            host += f":{parsed.port}"
        netloc = f"{credentials}@{host}"
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in {"currentschema", "current_schema"}
        ]
    )
    return urlunparse((scheme, netloc, parsed.path, "", query, ""))

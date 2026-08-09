"""工作区发布目标解析。

发布入口只在这里决定归属、租户、数据库类型和 schema，后续 DDL 与本体
元数据构建共享同一个不可变上下文。
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

DEFAULT_TENANT_ID = "dc_default_tenant"

OwnerType = Literal["personal", "enterprise"]
PublishDbType = Literal["SQLITE", "POSTGRESQL", "OPENGAUSS"]


class PublishConfigurationError(ValueError):
    """带稳定错误码的发布配置错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PublishContext:
    publish_id: str
    owner_type: OwnerType
    user_code: str
    tenant_id: str | None
    base_id: str
    datasource_alias: str
    db_type: PublishDbType
    connector_type: str
    schema_name: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "publish_id": self.publish_id,
            "owner_type": self.owner_type,
            "user_code": self.user_code,
            "tenant_id": self.tenant_id,
            "base_id": self.base_id,
            "datasource_alias": self.datasource_alias,
            "db_type": self.db_type,
            "connector_type": self.connector_type,
            "schema_name": self.schema_name,
        }


class PublishTargetResolver:
    """从请求和部署配置生成单次批量发布的固定上下文。"""

    def resolve(
        self,
        *,
        owner_type: str,
        user_code: str,
        tenant_id: str | None,
        base_id: str,
        publish_id: str | None = None,
        active_publication: dict[str, Any] | None = None,
    ) -> PublishContext:
        normalized_owner = owner_type.strip().lower()
        if normalized_owner not in {"personal", "enterprise"}:
            raise PublishConfigurationError(
                "INVALID_OWNER_TYPE", "owner_type 必须为 personal 或 enterprise"
            )
        resolved_owner = cast(OwnerType, normalized_owner)
        resolved_publish_id = publish_id or self._new_publish_id()

        if resolved_owner == "personal":
            return PublishContext(
                publish_id=resolved_publish_id,
                owner_type="personal",
                user_code=user_code,
                tenant_id=None,
                base_id=base_id,
                datasource_alias="personal_sqlite",
                db_type="SQLITE",
                connector_type="BYCLAW_SQL_EXECUTE",
                schema_name=None,
            )

        resolved_tenant = (tenant_id or "").strip() or DEFAULT_TENANT_ID
        self._validate_tenant_against_active(resolved_tenant, active_publication)
        db_type = self._enterprise_db_type()
        return PublishContext(
            publish_id=resolved_publish_id,
            owner_type="enterprise",
            user_code=user_code,
            tenant_id=resolved_tenant,
            base_id=base_id,
            datasource_alias=f"enterprise_{db_type.lower()}",
            db_type=db_type,
            connector_type=db_type,
            schema_name=self.schema_for_tenant(resolved_tenant),
        )

    @staticmethod
    def schema_for_tenant(tenant_id: str) -> str:
        digest = hashlib.sha256(tenant_id.encode()).hexdigest()[:12]
        return f"tenant_{digest}"

    @staticmethod
    def _enterprise_db_type() -> Literal["POSTGRESQL", "OPENGAUSS"]:
        raw = os.getenv("DATACLOUD_DB_TYPE", "postgresql").strip().upper()
        if not raw:
            raw = "POSTGRESQL"
        if raw not in {"POSTGRESQL", "OPENGAUSS"}:
            raise PublishConfigurationError(
                "ENTERPRISE_DB_TYPE_NOT_CONFIGURED",
                "DATACLOUD_DB_TYPE 必须配置为 postgresql 或 opengauss",
            )
        return cast(Literal["POSTGRESQL", "OPENGAUSS"], raw)

    @staticmethod
    def _validate_tenant_against_active(
        tenant_id: str,
        active_publication: dict[str, Any] | None,
    ) -> None:
        if not active_publication:
            return
        if active_publication.get("owner_type") != "enterprise":
            return
        active_tenant = active_publication.get("tenant_id")
        if active_tenant and active_tenant != tenant_id:
            raise PublishConfigurationError(
                "ENTERPRISE_TENANT_CHANGE_NOT_SUPPORTED",
                f"当前企业发布租户为 {active_tenant}，本期不支持变更为 {tenant_id}",
            )

    @staticmethod
    def _new_publish_id() -> str:
        now = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        return f"pub_{now}_{uuid.uuid4().hex[:10]}"

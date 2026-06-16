"""Pydantic schema unit tests — serialization, deserialization, validation."""

from __future__ import annotations

import pytest
from datacloud_server.api.schemas import (
    ActionDef,
    ApiResponse,
    DatasourceCreate,
    FieldDef,
    ObjectCreate,
    OntologyBaseCreate,
    OntologyBaseResponse,
    RelationCreate,
    ViewCreate,
    ok,
)


class TestApiResponse:
    """Unified response wrapper."""

    def test_defaults(self) -> None:
        r = ok()
        assert r.code == 200
        assert r.success is True
        assert r.message == "ok"
        assert r.data is None

    def test_with_data(self) -> None:
        r = ok(data={"key": "val"}, message="created")
        d = r.model_dump()
        assert d == {"code": 200, "success": True, "message": "created", "data": {"key": "val"}}

    def test_json_roundtrip(self) -> None:
        r = ok(data=[1, 2, 3])
        raw = r.model_dump_json()
        parsed = ApiResponse.model_validate_json(raw)
        assert parsed.code == 200
        assert parsed.data == [1, 2, 3]


class TestOntologyBaseCreate:
    """Create ontology base request validation."""

    def test_minimal_valid(self) -> None:
        ob = OntologyBaseCreate.model_validate({"baseId": "my_base", "displayName": "My Base"})
        d = ob.model_dump(by_alias=True)
        assert d["baseId"] == "my_base"
        assert d["displayName"] == "My Base"
        assert d["ownerType"] == "personal"
        assert d["timeoutSec"] == 30
        assert d["sourceUrl"] is None

    def test_full_fields(self) -> None:
        ob = OntologyBaseCreate.model_validate(
            {
                "baseId": "r_base",
                "displayName": "Remote",
                "ownerType": "enterprise",
                "sourceUrl": "https://example.com/api",
                "authType": "bearer",
                "authConfig": {"token": "secret"},
                "timeoutSec": 60,
                "description": "A remote base",
            }
        )
        d = ob.model_dump(by_alias=True)
        assert d["sourceUrl"] == "https://example.com/api"
        assert d["authType"] == "bearer"
        assert d["authConfig"] == {"token": "secret"}
        assert d["timeoutSec"] == 60

    def test_snake_case_input(self) -> None:
        """populate_by_name allows snake_case input too."""
        ob = OntologyBaseCreate.model_validate({"base_id": "b1", "display_name": "B1"})
        d = ob.model_dump(by_alias=True)
        assert d["baseId"] == "b1"

    def test_missing_required_raises(self) -> None:
        with pytest.raises(ValueError):
            OntologyBaseCreate.model_validate({"displayName": "No baseId"})

    def test_extra_fields_allowed(self) -> None:
        """extra='allow' lets unknown fields pass through."""
        ob = OntologyBaseCreate.model_validate(
            {
                "baseId": "b1",
                "displayName": "B1",
                "unknownField": 42,
            }
        )
        d = ob.model_dump(by_alias=True)
        assert "unknownField" in d


class TestOntologyBaseResponse:
    """Ontology base response."""

    def test_response_shape(self) -> None:
        obr = OntologyBaseResponse.model_validate(
            {
                "baseId": "b1",
                "displayName": "B1",
                "sourceType": "LOCAL",
                "ownerType": "personal",
            }
        )
        d = obr.model_dump(by_alias=True)
        assert d["baseId"] == "b1"
        assert d["sourceType"] == "LOCAL"
        assert d["createdAt"] == ""

    def test_json_roundtrip(self) -> None:
        obr = OntologyBaseResponse(
            baseId="b1",
            displayName="B1",
            sourceType="LOCAL",
            ownerType="personal",
            createdAt="2024-01-01",
        )
        raw = obr.model_dump_json(by_alias=True)
        parsed = OntologyBaseResponse.model_validate_json(raw)
        assert parsed.base_id == "b1"
        assert parsed.created_at == "2024-01-01"


class TestFieldDef:
    """Field definition."""

    def test_minimal(self) -> None:
        f = FieldDef.model_validate(
            {"fieldCode": "name", "fieldName": "Name", "fieldType": "STRING"}
        )
        d = f.model_dump(by_alias=True)
        assert d["fieldCode"] == "name"
        assert d["isPrimaryKey"] is False
        assert d["required"] is False

    def test_with_primary_key(self) -> None:
        f = FieldDef.model_validate(
            {
                "fieldCode": "id",
                "fieldName": "ID",
                "fieldType": "BIGINT",
                "isPrimaryKey": True,
                "required": True,
            }
        )
        assert f.is_primary_key is True
        assert f.required is True

    def test_extra_fields_allowed(self) -> None:
        f = FieldDef.model_validate(
            {
                "fieldCode": "x",
                "fieldName": "X",
                "fieldType": "STRING",
                "customProp": "value",
            }
        )
        d = f.model_dump(by_alias=True)
        assert d["customProp"] == "value"


class TestActionDef:
    """Action definition."""

    def test_minimal(self) -> None:
        a = ActionDef.model_validate({"actionCode": "create_customer"})
        d = a.model_dump(by_alias=True)
        assert d["actionCode"] == "create_customer"
        assert d["actionName"] == ""
        assert d["description"] == ""


class TestObjectCreate:
    """Object create request."""

    def test_minimal(self) -> None:
        oc = ObjectCreate.model_validate({"objectCode": "customer", "objectName": "Customer"})
        d = oc.model_dump(by_alias=True)
        assert d["objectCode"] == "customer"
        assert d["fields"] == []
        assert d["actions"] == []

    def test_with_fields_and_actions(self) -> None:
        oc = ObjectCreate.model_validate(
            {
                "objectCode": "customer",
                "objectName": "Customer",
                "fields": [{"fieldCode": "name", "fieldName": "Name", "fieldType": "STRING"}],
                "actions": [{"actionCode": "get_customer", "actionName": "Get Customer"}],
            }
        )
        d = oc.model_dump(by_alias=True)
        assert len(d["fields"]) == 1
        assert d["fields"][0]["fieldCode"] == "name"
        assert len(d["actions"]) == 1
        assert d["actions"][0]["actionCode"] == "get_customer"


class TestViewCreate:
    """View create request."""

    def test_minimal(self) -> None:
        vc = ViewCreate.model_validate({"viewCode": "sales_view", "viewName": "Sales View"})
        d = vc.model_dump(by_alias=True)
        assert d["viewCode"] == "sales_view"
        assert d["objectCodes"] == []

    def test_with_object_codes(self) -> None:
        vc = ViewCreate.model_validate(
            {
                "viewCode": "sales_view",
                "viewName": "Sales View",
                "objectCodes": ["customer", "order"],
            }
        )
        d = vc.model_dump(by_alias=True)
        assert d["objectCodes"] == ["customer", "order"]


class TestRelationCreate:
    """Relation create request."""

    def test_minimal(self) -> None:
        rc = RelationCreate.model_validate(
            {"relationCode": "has_order", "relationName": "Has Order"}
        )
        d = rc.model_dump(by_alias=True)
        assert d["relationCode"] == "has_order"

    def test_full(self) -> None:
        rc = RelationCreate.model_validate(
            {
                "relationCode": "has_order",
                "relationName": "Has Order",
                "sourceClass": "customer",
                "targetClass": "order",
                "relationType": "ONE_TO_MANY",
            }
        )
        d = rc.model_dump(by_alias=True)
        assert d["sourceClass"] == "customer"
        assert d["targetClass"] == "order"
        assert d["relationType"] == "ONE_TO_MANY"


class TestDatasourceCreate:
    """Datasource create request."""

    def test_minimal(self) -> None:
        dc = DatasourceCreate.model_validate({"dbId": "pg_main", "dbName": "Main PG"})
        d = dc.model_dump(by_alias=True)
        assert d["dbId"] == "pg_main"

    def test_full(self) -> None:
        dc = DatasourceCreate.model_validate(
            {
                "dbId": "pg_main",
                "dbName": "Main PG",
                "dbType": "opengauss",
                "host": "10.0.0.1",
                "port": 5432,
                "database": "postgres",
                "schema": "byai",
            }
        )
        d = dc.model_dump(by_alias=True)
        assert d["schema"] == "byai"
        assert d["port"] == 5432

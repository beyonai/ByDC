"""Pydantic model unit tests — serialization, deserialization, validation."""

from __future__ import annotations

import pytest
from datacloud_server.api.schemas import (
    OntologyBaseCreate,
    OntologyBaseResponse,
)
from datacloud_server.models import (
    Action,
    ApiResponse,
    Datasource,
    MetadataHit,
    ObjectType,
    ObjectTypeSummary,
    Property,
    Relation,
    Scene,
    SearchRequest,
    SearchResult,
    SearchTotalCount,
    View,
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

    def test_missing_required_raises(self) -> None:
        with pytest.raises(ValueError):
            OntologyBaseCreate.model_validate({"displayName": "No baseId"})

    def test_extra_fields_allowed(self) -> None:
        ob = OntologyBaseCreate.model_validate(
            {"baseId": "b1", "displayName": "B1", "unknownField": 42}
        )
        d = ob.model_dump(by_alias=True)
        assert "unknownField" in d


class TestOntologyBaseResponse:
    """Ontology base response."""

    def test_response_shape(self) -> None:
        obr = OntologyBaseResponse.model_validate(
            {"baseId": "b1", "displayName": "B1", "sourceType": "LOCAL", "ownerType": "personal"}
        )
        d = obr.model_dump(by_alias=True)
        assert d["baseId"] == "b1"
        assert d["sourceType"] == "LOCAL"
        assert d["createdAt"] == ""


class TestProperty:
    """Property definition — using propertyCode/propertyName/dataType naming."""

    def test_minimal(self) -> None:
        p = Property.model_validate(
            {"propertyCode": "name", "propertyName": "Name"}
        )
        d = p.model_dump(by_alias=True)
        assert d["propertyCode"] == "name"
        assert d["propertyName"] == "Name"
        assert d["dataType"] is None
        assert d["isRequired"] == 0

    def test_full(self) -> None:
        p = Property.model_validate(
            {
                "propertyCode": "id",
                "propertyName": "ID",
                "dataType": "BIGINT",
                "isRequired": 1,
                "isName": 1,
                "businessKey": 1,
                "sortNo": 10,
            }
        )
        d = p.model_dump(by_alias=True)
        assert d["dataType"] == "BIGINT"
        assert d["isRequired"] == 1
        assert d["sortNo"] == 10

    def test_extra_fields_allowed(self) -> None:
        p = Property.model_validate(
            {"propertyCode": "x", "propertyName": "X", "customProp": "value"}
        )
        d = p.model_dump(by_alias=True)
        assert d["customProp"] == "value"


class TestAction:
    """Action definition — full model with belongObjectCode."""

    def test_minimal(self) -> None:
        a = Action.model_validate(
            {"actionCode": "create_customer", "belongObjectCode": "customer"}
        )
        d = a.model_dump(by_alias=True)
        assert d["actionCode"] == "create_customer"
        assert d["actionName"] == ""
        assert d["belongObjectCode"] == "customer"

    def test_with_params(self) -> None:
        a = Action.model_validate(
            {
                "actionCode": "search",
                "actionName": "Search",
                "belongObjectCode": "cust",
                "params": [
                    {"paramCode": "keyword", "paramName": "Keyword", "paramType": "STRING", "isRequired": 1}
                ],
                "requestUrl": "/api/search",
                "requestMethod": "GET",
            }
        )
        d = a.model_dump(by_alias=True)
        assert d["params"][0]["paramCode"] == "keyword"
        assert d["params"][0]["isRequired"] == 1
        assert d["requestUrl"] == "/api/search"


class TestObjectType:
    """ObjectType definition — properties/actions not fields/actions."""

    def test_minimal(self) -> None:
        oc = ObjectType.model_validate({"objectCode": "customer", "objectName": "Customer"})
        d = oc.model_dump(by_alias=True)
        assert d["objectCode"] == "customer"
        assert d["properties"] == []
        assert d["actions"] == []

    def test_with_properties_and_actions(self) -> None:
        oc = ObjectType.model_validate(
            {
                "objectCode": "customer",
                "objectName": "Customer",
                "properties": [{"propertyCode": "name", "propertyName": "Name", "dataType": "STRING"}],
                "actions": [{"actionCode": "get_customer", "actionName": "Get Customer", "belongObjectCode": "customer"}],
            }
        )
        d = oc.model_dump(by_alias=True)
        assert len(d["properties"]) == 1
        assert d["properties"][0]["propertyCode"] == "name"
        assert len(d["actions"]) == 1
        assert d["actions"][0]["actionCode"] == "get_customer"


class TestObjectTypeSummary:
    """ObjectTypeSummary for listObjects."""

    def test_minimal(self) -> None:
        os_ = ObjectTypeSummary.model_validate({"objectCode": "cust", "objectName": "Customer"})
        d = os_.model_dump(by_alias=True)
        assert d["objectCode"] == "cust"
        assert d["fieldCount"] == 0

    def test_full(self) -> None:
        os_ = ObjectTypeSummary.model_validate(
            {"objectCode": "cust", "objectName": "Customer", "fieldCount": 3, "actionCount": 2}
        )
        d = os_.model_dump(by_alias=True)
        assert d["fieldCount"] == 3
        assert d["actionCount"] == 2


class TestView:
    """View definition."""

    def test_minimal(self) -> None:
        vc = View.model_validate({"viewCode": "sales_view", "viewName": "Sales View"})
        d = vc.model_dump(by_alias=True)
        assert d["viewCode"] == "sales_view"
        assert d["objectCodes"] == []

    def test_with_object_codes(self) -> None:
        vc = View.model_validate(
            {"viewCode": "sales_view", "viewName": "Sales View", "objectCodes": ["customer", "order"]}
        )
        d = vc.model_dump(by_alias=True)
        assert d["objectCodes"] == ["customer", "order"]


class TestRelation:
    """Relation definition — sourceObjectCode/targetObjectCode."""

    def test_minimal(self) -> None:
        rc = Relation.model_validate(
            {"relationCode": "has_order", "sourceObjectCode": "customer", "targetObjectCode": "order"}
        )
        d = rc.model_dump(by_alias=True)
        assert d["relationCode"] == "has_order"

    def test_full(self) -> None:
        rc = Relation.model_validate(
            {
                "relationCode": "has_order",
                "relationName": "Has Order",
                "sourceObjectCode": "customer",
                "targetObjectCode": "order",
                "relationCardinality": "ONE_TO_MANY",
            }
        )
        d = rc.model_dump(by_alias=True)
        assert d["sourceObjectCode"] == "customer"
        assert d["targetObjectCode"] == "order"
        assert d["relationCardinality"] == "ONE_TO_MANY"


class TestDatasource:
    """Datasource definition — nested db/doc/api (not flat)."""

    def test_minimal(self) -> None:
        dc = Datasource.model_validate({"db": [], "doc": [], "api": []})
        d = dc.model_dump(by_alias=True)
        assert d["db"] == []

    def test_with_db_connection(self) -> None:
        dc = Datasource.model_validate(
            {
                "db": [{"dbId": "pg_main", "dbCode": "main", "dbType": "opengauss"}],
                "doc": [],
                "api": [],
            }
        )
        d = dc.model_dump(by_alias=True)
        assert d["db"][0]["dbId"] == "pg_main"
        assert d["db"][0]["dbCode"] == "main"

    def test_nested_structure(self) -> None:
        """Datasource is nested, not flat."""
        dc = Datasource.model_validate(
            {
                "db": [
                    {"dbId": "pg1", "dbCode": "main", "dbType": "opengauss", "dbParams": {"host": "10.0.0.1", "port": 5432}}
                ],
                "doc": [{"docId": "d1", "docPath": "/docs/spec.pdf"}],
                "api": [{"apiId": "a1", "url": "https://api.example.com", "method": "GET"}],
            }
        )
        d = dc.model_dump(by_alias=True)
        assert len(d["db"]) == 1
        assert len(d["doc"]) == 1
        assert len(d["api"]) == 1
        assert d["db"][0]["dbParams"]["host"] == "10.0.0.1"


class TestScene:
    """Scene definition."""

    def test_minimal(self) -> None:
        sc = Scene.model_validate({"sceneId": "s1", "sceneName": "Sales", "sceneCode": "sales"})
        d = sc.model_dump(by_alias=True)
        assert d["sceneId"] == "s1"
        assert d["sceneCode"] == "sales"


class TestSearchRequest:
    """Search request."""

    def test_minimal(self) -> None:
        sr = SearchRequest.model_validate({"sceneId": "s1", "keyword": "test"})
        d = sr.model_dump(by_alias=True)
        assert d["keyword"] == "test"
        assert d["queryType"] == "vector"
        assert d["searchScope"] == "all"


class TestSearchResult:
    """Search result with metadata + instances."""

    def test_empty(self) -> None:
        sr = SearchResult()
        d = sr.model_dump(by_alias=True)
        assert d["metadata"] == []
        assert d["instances"] == []
        assert d["totalCount"]["metadata"] == 0

    def test_with_hits(self) -> None:
        sr = SearchResult(
            metadata=[MetadataHit(sceneId="s1", resultType="object", matchedField="cust", score=0.95)],
            instances=[],
            totalCount=SearchTotalCount(metadata=1, instances=0),
        )
        d = sr.model_dump(by_alias=True)
        assert len(d["metadata"]) == 1
        assert d["metadata"][0]["matchedField"] == "cust"
        assert d["totalCount"]["metadata"] == 1

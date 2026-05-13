from pathlib import Path

import pytest
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.owl_parser import (
    OwlParser,
    ParsedAction,
    ParsedField,
    ParsedObject,
)


def test_owl_parser_synthesizes_function_from_request_url() -> None:
    parser = OwlParser()
    parser._objects["todo_items"] = ParsedObject(
        object_code="todo_items",
        object_name="待办",
        source_type="API",
        actions=["create_todo"],
    )
    parser._actions["create_todo"] = ParsedAction(
        action_code="create_todo",
        action_name="创建待办",
        action_type="operation",
        belong_class="todo_items",
        function_refs=[],
        request_url="http://127.0.0.1:8001/api/v1/todos",
        request_method="POST",
    )

    content = parser.parse_directory(Path("/tmp/parser_not_used"))

    action = content["objects"][0]["actions"][0]
    assert action["function_refs"] == ["fn_create_todo"]
    assert content["functions"] == {
        "fn_create_todo": {
            "openapi": "3.0.3",
            "info": {"title": "创建待办", "version": "1.0.0"},
            "servers": [{"url": "http://127.0.0.1:8001"}],
            "paths": {
                "/api/v1/todos": {
                    "post": {
                        "summary": "创建待办",
                        "responses": {"200": {"description": "创建待办结果"}},
                    }
                }
            },
        }
    }


def test_loader_can_use_parser_generated_action_and_function() -> None:
    parser = OwlParser()
    parser._objects["todo_items"] = ParsedObject(
        object_code="todo_items",
        object_name="待办",
        source_type="API",
        actions=["create_todo"],
    )
    parser._actions["create_todo"] = ParsedAction(
        action_code="create_todo",
        action_name="创建待办",
        action_type="operation",
        belong_class="todo_items",
        function_refs=[],
        request_url="http://127.0.0.1:8001/api/v1/todos",
        request_method="POST",
    )

    content = parser.parse_directory(Path("/tmp/parser_not_used"))

    loader = OntologyLoader()
    loader._load_from_owl_content(content)

    cls = loader.get_ontology_class("todo_items")
    assert cls.actions[0].function_refs == ["fn_create_todo"]
    assert loader.get_function_config("fn_create_todo") == {
        "openapi": "3.0.3",
        "info": {"title": "创建待办", "version": "1.0.0"},
        "servers": [{"url": "http://127.0.0.1:8001"}],
        "paths": {
            "/api/v1/todos": {
                "post": {
                    "summary": "创建待办",
                    "responses": {"200": {"description": "创建待办结果"}},
                }
            }
        },
    }


def test_owl_parser_builds_request_and_response_schema_from_action_params() -> None:
    parser = OwlParser()
    parser._objects["po_organization"] = ParsedObject(
        object_code="po_organization",
        object_name="组织",
        source_type="API",
        actions=["query_org_by_name_or_id"],
    )
    parser._actions["query_org_by_name_or_id"] = ParsedAction(
        action_code="query_org_by_name_or_id",
        action_name="按名称或ID查询组织",
        description="按组织ID列表或名称列表批量查询组织详情",
        action_type="query",
        belong_class="po_organization",
        function_refs=["fn_po_org_query_by_ids"],
        request_param_refs=["req_org_ids"],
        response_param_refs=["resp_org_id"],
        request_url="http://127.0.0.1:8001/api/v1/po/organizations/query",
        request_method="POST",
    )
    parser._request_params_by_uri["req_org_ids"] = ParsedField(
        field_code="orgIds",
        field_name="组织ID或名称列表",
        field_type="ARRAY",
        required=False,
        mapping_path="$.requestBody.orgIds",
    )
    parser._response_params_by_uri["resp_org_id"] = ParsedField(
        field_code="orgId",
        field_name="组织ID",
        field_type="STRING",
        required=False,
        mapping_path="$.organizations[].orgId",
    )

    content = parser.parse_directory(Path("/tmp/parser_not_used"))

    operation = content["functions"]["fn_po_org_query_by_ids"]["paths"][
        "/api/v1/po/organizations/query"
    ]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "type": "object",
        "properties": {
            "orgIds": {
                "type": "array",
                "items": {"type": "string"},
                "description": "组织ID或名称列表",
            }
        },
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "type": "object",
        "properties": {
            "organizations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "orgId": {
                            "type": "string",
                            "description": "组织ID",
                        }
                    },
                },
            }
        },
    }


def test_owl_response_param_name_falls_back_to_object_property_label() -> None:
    parser = OwlParser()
    parser._objects["todo_items"] = ParsedObject(
        object_code="todo_items",
        object_name="待办",
        source_type="API",
        actions=["query_todo"],
    )
    parser._object_fields["todo_items"]["todoId"] = ParsedField(
        field_code="todoId",
        field_name="待办ID",
        field_type="STRING",
    )
    parser._actions["query_todo"] = ParsedAction(
        action_code="query_todo",
        action_name="查询待办",
        action_type="query",
        belong_class="todo_items",
        function_refs=["fn_query_todo"],
        response_param_refs=["resp_todo_id"],
    )
    parser._response_params_by_uri["resp_todo_id"] = ParsedField(
        field_code="todoId",
        field_name="todoId",
        field_type="STRING",
        mapping_path="$.data[].todoId",
        object_property="todoId",
    )

    content = parser.parse_directory(Path("/tmp/parser_not_used"))

    action = content["objects"][0]["actions"][0]
    assert action["params"][0]["param_name"] == "待办ID"


def test_owl_parser_builds_openapi_parameters_for_get_action() -> None:
    parser = OwlParser()
    parser._objects["po_users"] = ParsedObject(
        object_code="po_users",
        object_name="人员",
        source_type="API",
        actions=["query_user_detail"],
    )
    parser._actions["query_user_detail"] = ParsedAction(
        action_code="query_user_detail",
        action_name="查询人员详情",
        description="按用户ID查询人员详情",
        action_type="query",
        belong_class="po_users",
        function_refs=["fn_query_user_detail"],
        request_param_refs=["req_user_id", "req_keyword"],
        request_url="http://127.0.0.1:8001/api/v1/users/{userId}",
        request_method="GET",
    )
    parser._request_params_by_uri["req_user_id"] = ParsedField(
        field_code="userId",
        field_name="用户ID",
        field_type="STRING",
        required=True,
        mapping_path="$.path.userId",
    )
    parser._request_params_by_uri["req_keyword"] = ParsedField(
        field_code="keyword",
        field_name="关键字",
        field_type="STRING",
        required=False,
        mapping_path="$.query.keyword",
    )

    content = parser.parse_directory(Path("/tmp/parser_not_used"))

    operation = content["functions"]["fn_query_user_detail"]["paths"]["/api/v1/users/{userId}"][
        "get"
    ]
    assert "requestBody" not in operation
    assert operation["parameters"] == [
        {
            "name": "userId",
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
            "description": "用户ID",
        },
        {
            "name": "keyword",
            "in": "query",
            "required": False,
            "schema": {"type": "string"},
            "description": "关键字",
        },
    ]


def test_owl_parser_builds_root_array_request_body_schema() -> None:
    parser = OwlParser()
    parser._objects["todo_items"] = ParsedObject(
        object_code="todo_items",
        object_name="待办",
        source_type="API",
        actions=["accept_todo_batch"],
    )
    parser._actions["accept_todo_batch"] = ParsedAction(
        action_code="accept_todo_batch",
        action_name="批量接收待办",
        description="根数组 body 示例",
        action_type="operation",
        belong_class="todo_items",
        function_refs=["fn_accept_todo_batch"],
        request_param_refs=["req_user_id", "req_user_code"],
        request_url="http://127.0.0.1:8001/api/v1/todos/accept/batch",
        request_method="POST",
    )
    parser._request_params_by_uri["req_user_id"] = ParsedField(
        field_code="userId",
        field_name="用户ID",
        field_type="STRING",
        required=True,
        mapping_path="$.requestBody.[].user_id",
    )
    parser._request_params_by_uri["req_user_code"] = ParsedField(
        field_code="userCode",
        field_name="用户编码",
        field_type="STRING",
        required=False,
        mapping_path="$.requestBody.[].user_code",
    )

    content = parser.parse_directory(Path("/tmp/parser_not_used"))
    operation = content["functions"]["fn_accept_todo_batch"]["paths"]["/api/v1/todos/accept/batch"][
        "post"
    ]

    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "用户ID",
                },
                "user_code": {
                    "type": "string",
                    "description": "用户编码",
                },
            },
            "required": ["user_id"],
        },
    }


def test_owl_parser_reads_custom_type_instead_of_rdf_type(tmp_path: Path) -> None:
    pytest.importorskip("rdflib")

    owl_path = tmp_path / "create_todo.owl"
    owl_path.write_text(
        """<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/action/ontology#">
    <owl:Class rdf:about="#ActionDefinition"/>
    <owl:Class rdf:about="#RequestParameter"/>
    <owl:NamedIndividual rdf:about="#action_create_todo">
        <rdf:type rdf:resource="#ActionDefinition"/>
        <action_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">create_todo</action_code>
        <action_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">创建待办</action_name>
        <action_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">OPERATION</action_type>
        <belong_entity rdf:datatype="http://www.w3.org/2001/XMLSchema#string">["todo_items"]</belong_entity>
        <request_params rdf:resource="#param_create_todo_handlerIds_0"/>
    </owl:NamedIndividual>
    <owl:NamedIndividual rdf:about="#param_create_todo_handlerIds_0">
        <rdf:type rdf:resource="#RequestParameter"/>
        <paramCode rdf:datatype="http://www.w3.org/2001/XMLSchema#string">handlerIds</paramCode>
        <type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">array</type>
        <description rdf:datatype="http://www.w3.org/2001/XMLSchema#string">处理人ID或名称列表</description>
        <isRequired rdf:datatype="http://www.w3.org/2001/XMLSchema#boolean">false</isRequired>
    </owl:NamedIndividual>
</rdf:RDF>
""",
        encoding="utf-8",
    )

    parser = OwlParser()
    parser.parse_file(owl_path)

    request_param = parser._request_params_by_uri[
        "http://example.org/action/ontology#param_create_todo_handlerIds_0"
    ]
    assert request_param.field_type == "ARRAY"


def test_owl_parser_parse_resource_directory_returns_legacy_content_shape() -> None:
    pytest.importorskip("rdflib")

    resource_dir = (
        Path(__file__).resolve().parents[2] / "src" / "datacloud_data_service" / "resource"
    )

    parser = OwlParser()
    content = parser.parse_resource_directory(resource_dir)

    enterprise = next(
        obj for obj in content["objects"] if obj["object_code"] == "ads_enterprise_analysis"
    )
    assert enterprise["datasource_alias"] == "whale_datacloud"
    assert enterprise["table_name"] == "ads_enterprise_analysis"
    assert any(field["field_code"] == "enterprise_id" for field in enterprise["fields"])
    assert "onto_crm" in content["datasource_configs"]

    rel = next(
        relation
        for relation in content["relations"]
        if relation["relation_code"] == "rel_ads_enterprise_analysis_to_ads_grid_analysis"
    )
    assert rel["source_class"] == "ads_enterprise_analysis"
    assert rel["target_class"] == "ads_grid_analysis"

    scene = next(
        view for view in content["views"] if view["view_id"] == "scene_enterprise_analysis"
    )
    assert any(obj["object_code"] == "ads_enterprise_analysis" for obj in scene["objects"])


def test_owl_parser_parse_resource_directory_filters_objects() -> None:
    pytest.importorskip("rdflib")

    resource_dir = (
        Path(__file__).resolve().parents[2] / "src" / "datacloud_data_service" / "resource"
    )

    parser = OwlParser()
    content = parser.parse_resource_directory(
        resource_dir,
        object_codes=["ads_enterprise_analysis"],
    )

    assert [obj["object_code"] for obj in content["objects"]] == ["ads_enterprise_analysis"]
    assert content["views"] == []


def test_owl_parser_empty_filters_load_all() -> None:
    pytest.importorskip("rdflib")

    resource_dir = (
        Path(__file__).resolve().parents[2] / "src" / "datacloud_data_service" / "resource"
    )

    parser = OwlParser()
    content = parser.parse_resource_directory(
        resource_dir,
        object_codes=[],
        view_codes=[],
    )

    object_codes = {obj["object_code"] for obj in content["objects"]}
    view_codes = {view["view_id"] for view in content["views"]}
    assert "ads_enterprise_analysis" in object_codes
    assert "scene_enterprise_analysis" in view_codes


def test_owl_parser_parse_resource_directory_loads_view_related_objects() -> None:
    pytest.importorskip("rdflib")

    resource_dir = (
        Path(__file__).resolve().parents[2] / "src" / "datacloud_data_service" / "resource"
    )

    parser = OwlParser()
    content = parser.parse_resource_directory(
        resource_dir,
        view_codes=["scene_enterprise_analysis"],
    )

    object_codes = {obj["object_code"] for obj in content["objects"]}
    assert object_codes == {
        "ads_chain_analysis",
        "ads_enterprise_analysis",
        "ads_grid_analysis",
        "ads_manage_grid_analysis",
    }
    assert [view["view_id"] for view in content["views"]] == ["scene_enterprise_analysis"]

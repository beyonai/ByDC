from __future__ import annotations

from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.models import OntologyClass, OntologyField
from datacloud_data_sdk.ontology.term_loader import KbTermLoader
from datacloud_platform.execution.virtual_action_injector import inject_virtual_actions


def test_inject_virtual_actions_adds_dynamic_table_write_actions() -> None:
    loader = OntologyLoader()
    loader._classes["sales_note"] = OntologyClass(
        object_code="sales_note",
        object_name="销售记录",
        description="",
        source_type="DYNAMIC_TABLE",
        datasource_alias="dynamic_table",
        table_name="sales_note",
        fields=[
            OntologyField("id", "ID", "INTEGER", is_primary_key=True),
            OntologyField("customer_name", "客户名称", "STRING"),
            OntologyField(
                "amount",
                "金额",
                "NUMBER",
                analytic_role="measure",
                aggregate_ops=["sum"],
            ),
        ],
        actions=[],
    )

    inject_virtual_actions(loader)

    cls = loader.get_ontology_class("sales_note")
    action_codes = {action.action_code for action in cls.actions}
    assert {
        "query_sales_note",
        "compute_sales_note",
        "insert_sales_note",
        "update_sales_note",
        "delete_sales_note",
    }.issubset(action_codes)

    insert_action = next(
        action for action in cls.actions if action.action_code == "insert_sales_note"
    )
    insert_schema = insert_action.input_schema or {}
    record_schema = insert_schema["properties"]["records"]["items"]
    assert "id" not in record_schema["properties"]


def test_inject_virtual_actions_adds_dict_term_values_to_filter_schema() -> None:
    """虚拟查询动作的 dict 术语字段应把具体术语值给到模型。"""
    loader = OntologyLoader()
    loader.configure(
        term_loader=KbTermLoader(
            {
                "status.code": [
                    {"code": "TODO", "label": "待办"},
                    {"code": "DONE", "label": "已完成"},
                ]
            }
        )
    )
    loader._classes["todo_item"] = OntologyClass(
        object_code="todo_item",
        object_name="待办事项",
        description="",
        source_type="DB",
        datasource_alias="main",
        table_name="todo_item",
        fields=[
            OntologyField("id", "ID", "INTEGER", is_primary_key=True),
            OntologyField(
                "status",
                "状态",
                "STRING",
                term_set="status.code",
                term_type="enum",
                analytic_role="dimension",
                analytic_kind="name",
                filter_ops=["eq", "in", "is_null", "is_not_null"],
            ),
        ],
        actions=[],
    )

    inject_virtual_actions(loader)

    cls = loader.get_ontology_class("todo_item")
    query_action = next(action for action in cls.actions if action.action_code == "query_todo_item")
    query_schema = query_action.input_schema or {}
    filter_items = query_schema["properties"]["filters"]["items"]["oneOf"]
    status_item = next(
        item for item in filter_items if item["properties"]["field"].get("enum") == ["status"]
    )
    value_schema = status_item["properties"]["value"]

    assert "待办" in query_action.description
    assert "已完成" in query_action.description
    assert "待办" in value_schema["description"]
    assert "已完成" in value_schema["description"]
    assert {"type": "string", "enum": ["待办", "已完成"]} in value_schema["oneOf"]
    assert {
        "type": "array",
        "items": {"type": "string", "enum": ["待办", "已完成"]},
    } in value_schema["oneOf"]


def test_inject_virtual_actions_adds_kb_write_action() -> None:
    loader = OntologyLoader()
    loader._classes["meeting_doc"] = OntologyClass(
        object_code="meeting_doc",
        object_name="会议文档",
        description="",
        source_type="KNOWLEDGE_BASE",
        datasource_alias="kb_docs",
        fields=[OntologyField("status", "状态", "STRING")],
        actions=[],
    )

    inject_virtual_actions(loader)

    cls = loader.get_ontology_class("meeting_doc")
    action_codes = {action.action_code for action in cls.actions}
    assert {
        "search_meeting_doc",
        "search_by_file_name_meeting_doc",
        "write_meeting_doc",
    }.issubset(action_codes)
    search_action = next(
        action for action in cls.actions if action.action_code == "search_meeting_doc"
    )
    search_schema = search_action.input_schema or {}
    assert set(search_schema["properties"]) == {
        "query",
        "filters",
        "filter_relation",
        "order_by",
        "limit",
        "offset",
    }
    file_name_search_action = next(
        action for action in cls.actions if action.action_code == "search_by_file_name_meeting_doc"
    )
    file_name_search_schema = file_name_search_action.input_schema or {}
    assert set(file_name_search_schema["properties"]) == {"query", "fileName"}
    assert file_name_search_schema["required"] == ["query", "fileName"]
    write_action = next(
        action for action in cls.actions if action.action_code == "write_meeting_doc"
    )
    write_schema = write_action.input_schema or {}
    assert write_schema["properties"]["labels"]["properties"]["status"]["type"] == "string"
    assert (
        write_schema["properties"]["records"]["items"]["properties"]["labels"]["properties"][
            "status"
        ]["type"]
        == "string"
    )

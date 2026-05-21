from __future__ import annotations

from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.models import OntologyClass, OntologyField
from datacloud_data_service.tools.virtual_action_injector import inject_virtual_actions


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
    record_schema = insert_action.input_schema["properties"]["records"]["items"]
    assert "id" not in record_schema["properties"]


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
    file_name_search_action = next(
        action for action in cls.actions if action.action_code == "search_by_file_name_meeting_doc"
    )
    assert set(file_name_search_action.input_schema["properties"]) == {"query", "fileName"}
    assert file_name_search_action.input_schema["required"] == ["query", "fileName"]
    write_action = next(
        action for action in cls.actions if action.action_code == "write_meeting_doc"
    )
    assert (
        write_action.input_schema["properties"]["labels"]["properties"]["status"]["type"]
        == "string"
    )

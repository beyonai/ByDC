"""generate_from_definition 单元测试 — 先红后绿。

测试从 workspace_state dict 生成 OWL 文件的编排逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture()
def object_state() -> dict[str, Any]:
    return {
        "entity_code": "by_test",
        "entity_name": "测试对象",
        "entity_desc": "用于测试的对象",
        "entity_source": "DYNAMIC_TABLE",
        "library_code": "PERSONAL_LIB",
        "library_name": "个人本体库",
        "domain_code": "PERSONAL_DOMAIN",
        "domain_name": "个人领域",
        "db_code": "personal_sqlite",
        "db_type": "PERSONAL_SQLITE",
        "fields": [
            {
                "property_code": "title",
                "property_name": "标题",
                "data_type": "STRING",
                "ext_property": {
                    "property_role_rule": {"property_role": "DIMENSION", "rule_type": "name"}
                },
            },
            {
                "property_code": "status",
                "property_name": "状态",
                "data_type": "STRING",
                "ext_property": {
                    "property_role_rule": {"property_role": "DIMENSION", "rule_type": "description"}
                },
            },
        ],
    }


@pytest.fixture()
def view_state() -> dict[str, Any]:
    return {
        "view_code": "v_test",
        "view_name": "测试视图",
        "view_desc": "用于测试的视图",
        "library_code": "PERSONAL_LIB",
        "library_name": "个人本体库",
        "domain_code": "PERSONAL_DOMAIN",
        "domain_name": "个人领域",
        "object_codes": ["by_task", "by_user"],
        "object_relations": [
            {
                "source_object_code": "by_task",
                "source_object_field_code": "user_id",
                "target_object_code": "by_user",
                "target_object_field_code": "id",
                "relation_type": "MANY_TO_ONE",
            }
        ],
    }


# ── 基本调用 ───────────────────────────────────────────────────────────────────


def test_generate_from_definition_calls_generate_from_tables(
    object_state: dict[str, Any], tmp_path: Path
) -> None:
    """generate_from_definition 应调用 generate_from_tables。"""
    from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_definition

    with patch(
        "datacloud_knowledge.ingestion.owl_generate.generator.generate_from_tables"
    ) as mock_gen:
        generate_from_definition(object_state, tmp_path)
    mock_gen.assert_called_once()


def test_generate_from_definition_passes_output_dir(
    object_state: dict[str, Any], tmp_path: Path
) -> None:
    """output_dir 应正确传递给 generate_from_tables。"""
    from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_definition

    with patch(
        "datacloud_knowledge.ingestion.owl_generate.generator.generate_from_tables"
    ) as mock_gen:
        generate_from_definition(object_state, tmp_path)
    config_arg = mock_gen.call_args[0][0]
    assert config_arg.output_dir == tmp_path


def test_generate_from_definition_entity_code_in_table_codes(
    object_state: dict[str, Any], tmp_path: Path
) -> None:
    """entity_code 应出现在 config.table_codes 中。"""
    from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_definition

    with patch(
        "datacloud_knowledge.ingestion.owl_generate.generator.generate_from_tables"
    ) as mock_gen:
        generate_from_definition(object_state, tmp_path)
    config_arg = mock_gen.call_args[0][0]
    assert "by_test" in config_arg.table_codes


def test_generate_from_definition_entity_name_in_table_names(
    object_state: dict[str, Any], tmp_path: Path
) -> None:
    """entity_name 应出现在 config.table_names 中。"""
    from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_definition

    with patch(
        "datacloud_knowledge.ingestion.owl_generate.generator.generate_from_tables"
    ) as mock_gen:
        generate_from_definition(object_state, tmp_path)
    config_arg = mock_gen.call_args[0][0]
    assert config_arg.table_names.get("by_test") == "测试对象"


def test_generate_from_definition_fields_become_columns(
    object_state: dict[str, Any], tmp_path: Path
) -> None:
    """fields 应转换为 Table.columns 传入 generate_from_tables。"""
    from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_definition

    with patch(
        "datacloud_knowledge.ingestion.owl_generate.generator.generate_from_tables"
    ) as mock_gen:
        generate_from_definition(object_state, tmp_path)
    tables_arg: list[Any] = mock_gen.call_args[0][1]
    assert len(tables_arg) == 1
    table = tables_arg[0]
    col_names = [c.name for c in table.columns]
    assert "title" in col_names
    assert "status" in col_names


def test_generate_from_definition_field_roles_mapped(
    object_state: dict[str, Any], tmp_path: Path
) -> None:
    """ext_property.property_role_rule 应映射到 config.field_roles。"""
    from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_definition

    with patch(
        "datacloud_knowledge.ingestion.owl_generate.generator.generate_from_tables"
    ) as mock_gen:
        generate_from_definition(object_state, tmp_path)
    config_arg = mock_gen.call_args[0][0]
    role = config_arg.field_roles.get(("by_test", "title"))
    assert role is not None
    assert role.property_role == "DIMENSION"
    assert role.rule_type == "name"


def test_generate_from_definition_library_code_passed(
    object_state: dict[str, Any], tmp_path: Path
) -> None:
    from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_definition

    with patch(
        "datacloud_knowledge.ingestion.owl_generate.generator.generate_from_tables"
    ) as mock_gen:
        generate_from_definition(object_state, tmp_path)
    config_arg = mock_gen.call_args[0][0]
    assert config_arg.library_code == "PERSONAL_LIB"


def test_generate_from_definition_db_code_passed(
    object_state: dict[str, Any], tmp_path: Path
) -> None:
    from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_definition

    with patch(
        "datacloud_knowledge.ingestion.owl_generate.generator.generate_from_tables"
    ) as mock_gen:
        generate_from_definition(object_state, tmp_path)
    config_arg = mock_gen.call_args[0][0]
    assert config_arg.db_code == "personal_sqlite"


# ── 视图 state ─────────────────────────────────────────────────────────────────


def test_generate_from_definition_view_state_sets_view_code(
    view_state: dict[str, Any], tmp_path: Path
) -> None:
    """视图 state 应设置 config.view_code。"""
    from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_definition

    with patch(
        "datacloud_knowledge.ingestion.owl_generate.generator.generate_from_tables"
    ) as mock_gen:
        generate_from_definition(view_state, tmp_path)
    config_arg = mock_gen.call_args[0][0]
    assert config_arg.view_code == "v_test" or any(
        v.view_code == "v_test" for v in config_arg.views
    )


def test_generate_from_definition_view_object_relations_mapped(
    view_state: dict[str, Any], tmp_path: Path
) -> None:
    """object_relations 应映射到 config.object_relations。"""
    from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_definition

    with patch(
        "datacloud_knowledge.ingestion.owl_generate.generator.generate_from_tables"
    ) as mock_gen:
        generate_from_definition(view_state, tmp_path)
    config_arg = mock_gen.call_args[0][0]
    assert len(config_arg.object_relations) == 1
    rel = config_arg.object_relations[0]
    assert rel.source_code == "by_task"
    assert rel.target_code == "by_user"


# ── term_type_code 绑定 ────────────────────────────────────────────────────────


def test_generate_from_definition_term_type_code_binding(tmp_path: Path) -> None:
    """fields 中有 term_type_code 时，应生成 TermBinding。"""
    from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_definition

    state: dict[str, Any] = {
        "entity_code": "by_test",
        "entity_name": "测试对象",
        "entity_source": "DYNAMIC_TABLE",
        "library_code": "PERSONAL_LIB",
        "domain_code": "PERSONAL_DOMAIN",
        "db_code": "personal_sqlite",
        "db_type": "PERSONAL_SQLITE",
        "fields": [
            {
                "property_code": "handler_name",
                "property_name": "处理人",
                "data_type": "STRING",
                "term_type_code": "user_name",
                "ext_property": {},
            }
        ],
    }
    with patch(
        "datacloud_knowledge.ingestion.owl_generate.generator.generate_from_tables"
    ) as mock_gen:
        generate_from_definition(state, tmp_path)
    config_arg = mock_gen.call_args[0][0]
    binding_type_codes = [b.term_type_code for b in config_arg.term_bindings]
    assert "user_name" in binding_type_codes

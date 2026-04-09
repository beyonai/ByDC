"""OntologyValidator 校验 property_kind 与配置一致性。"""

import pytest

from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.validator import OntologyValidator


def test_derived_without_derived_config_fails() -> None:
    """derived 字段无 derived_config 时校验失败。"""
    content = {
        "objects": [
            {
                "object_code": "test_obj",
                "object_name": "测试对象",
                "source_type": "DB",
                "fields": [
                    {
                        "field_code": "bad_derived",
                        "field_name": "错误派生",
                        "field_type": "NUMBER",
                        "property_kind": "derived",
                        # 缺少 derived_config
                    },
                ],
                "actions": [],
            }
        ],
        "relations": [],
    }
    loader = OntologyLoader()
    loader.load_from_content(content)
    errors = OntologyValidator.validate(loader)
    assert len(errors) >= 1
    assert any("derived" in e.lower() and "derived_config" in e.lower() for e in errors)


def test_linked_without_relation_ref_fails() -> None:
    """linked 字段无 relation_ref 时校验失败。"""
    content = {
        "objects": [
            {
                "object_code": "test_obj",
                "object_name": "测试对象",
                "source_type": "DB",
                "fields": [
                    {
                        "field_code": "bad_linked",
                        "field_name": "错误关联",
                        "field_type": "ARRAY",
                        "property_kind": "linked",
                        # 缺少 relation_ref
                    },
                ],
                "actions": [],
            }
        ],
        "relations": [],
    }
    loader = OntologyLoader()
    loader.load_from_content(content)
    errors = OntologyValidator.validate(loader)
    assert len(errors) >= 1
    assert any("linked" in e.lower() and "relation_ref" in e.lower() for e in errors)


def test_api_linked_field_without_resolve_action_code_fails() -> None:
    """API 对象 linked 字段，且 Relation 无 resolve_action_code、字段也无 resolve_action_code 时校验失败。"""
    content = {
        "objects": [
            {
                "object_code": "customer",
                "object_name": "客户",
                "source_type": "API",
                "fields": [
                    {"field_code": "customer_id", "field_name": "客户ID", "field_type": "STRING"},
                    {
                        "field_code": "opportunities",
                        "field_name": "商机列表",
                        "field_type": "ARRAY",
                        "property_kind": "linked",
                        "relation_ref": "customer_has_opportunities",
                        # 字段无 resolve_action_code
                    },
                ],
                "actions": [
                    {
                        "action_code": "query_customers",
                        "action_name": "查客户",
                        "action_type": "query",
                        "params": [],
                        "function_refs": [],
                    },
                ],
            },
            {
                "object_code": "sales_opportunity",
                "object_name": "商机",
                "source_type": "API",
                "fields": [{"field_code": "id", "field_name": "ID", "field_type": "STRING"}],
                "actions": [],
            },
        ],
        "relations": [
            {
                "relation_code": "customer_has_opportunities",
                "source_class": "customer",
                "target_class": "sales_opportunity",
                "relation_type": "ONE_TO_MANY",
                # Relation 无 resolve_action_code
            },
        ],
    }
    loader = OntologyLoader()
    loader.load_from_content(content)
    errors = OntologyValidator.validate(loader)
    assert len(errors) >= 1
    assert any("resolve" in e.lower() or "linked" in e.lower() for e in errors)


def test_valid_derived_and_linked_passes() -> None:
    """derived 有 derived_config、linked 有 relation_ref 且 API 有 resolve 时校验通过。"""
    content = {
        "objects": [
            {
                "object_code": "test_obj",
                "object_name": "测试对象",
                "source_type": "DB",
                "fields": [
                    {
                        "field_code": "amount",
                        "field_name": "金额",
                        "field_type": "NUMBER",
                        "source_column": "amount",
                    },
                    {
                        "field_code": "discount_amount",
                        "field_name": "折后金额",
                        "field_type": "NUMBER",
                        "property_kind": "derived",
                        "derived_config": {
                            "mode": "expression",
                            "expression": "amount * 0.9",
                            "depends_on": ["amount"],
                        },
                    },
                    {
                        "field_code": "opportunities",
                        "field_name": "商机列表",
                        "field_type": "ARRAY",
                        "property_kind": "linked",
                        "relation_ref": "cust_opp",
                    },
                ],
                "actions": [],
            },
        ],
        "relations": [
            {
                "relation_code": "cust_opp",
                "source_class": "test_obj",
                "target_class": "opp",
                "relation_type": "ONE_TO_MANY",
            },
        ],
    }
    loader = OntologyLoader()
    loader.load_from_content(content)
    errors = OntologyValidator.validate(loader)
    assert len(errors) == 0


def test_api_linked_with_resolve_action_code_passes() -> None:
    """API 对象 linked 字段，Relation 有 resolve_action_code 时校验通过。"""
    content = {
        "objects": [
            {
                "object_code": "customer",
                "object_name": "客户",
                "source_type": "API",
                "fields": [
                    {"field_code": "customer_id", "field_name": "客户ID", "field_type": "STRING"},
                    {
                        "field_code": "opportunities",
                        "field_name": "商机列表",
                        "field_type": "ARRAY",
                        "property_kind": "linked",
                        "relation_ref": "customer_has_opportunities",
                    },
                ],
                "actions": [
                    {
                        "action_code": "query_customers",
                        "action_name": "查客户",
                        "action_type": "query",
                        "params": [],
                        "function_refs": [],
                    },
                    {
                        "action_code": "query_opp_by_cust",
                        "action_name": "按客户查商机",
                        "action_type": "query",
                        "params": [],
                        "function_refs": [],
                    },
                ],
            },
            {
                "object_code": "sales_opportunity",
                "object_name": "商机",
                "source_type": "API",
                "fields": [],
                "actions": [],
            },
        ],
        "relations": [
            {
                "relation_code": "customer_has_opportunities",
                "source_class": "customer",
                "target_class": "sales_opportunity",
                "relation_type": "ONE_TO_MANY",
                "resolve_action_code": "query_opp_by_cust",
                "resolve_param_binding": {
                    "source_field": "customer_id",
                    "action_param": "customerId",
                },
            },
        ],
    }
    loader = OntologyLoader()
    loader.load_from_content(content)
    errors = OntologyValidator.validate(loader)
    assert len(errors) == 0

import json
import sys

sys.path.insert(0, "scripts")
import logging
import os

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")


def _load_sdk():
    try:
        from datacloud_data_sdk.ontology.owl_builder import ObjectOwlBuilder
        from datacloud_data_sdk.ontology.owl_packager import pack_to_zip
        from datacloud_data_sdk.ontology.schema_validator import validate_object
        from datacloud_data_sdk.ontology.utils import chinese_to_entity_code

        return ObjectOwlBuilder, pack_to_zip, validate_object, chinese_to_entity_code
    except ImportError as e:
        print(json.dumps({"ok": False, "error": f"SDK 未安装: {e}"}), flush=True)
        sys.exit(1)


def datasource():
    return {
        "db_code": "personal_sqlite",
        "db_type": "PERSONAL_SQLITE",
        "db_params": {
            "endpoint_url": os.environ.get("SQLITE_API_URL", "{{SQLITE_API_URL}}"),
            "user_code": os.environ.get("USER_CODE", "{{USER_CODE}}"),
        },
    }


data = {
    "entity_name": "产品信息",
    "entity_desc": "产品主数据",
    "fields": [
        {
            "property_code": "product_name",
            "property_name": "产品名称",
            "data_type": "VARCHAR",
            "is_required": True,
            "ext_property": {
                "property_role_rule": {"property_role": "DIMENSION", "rule_type": "name"}
            },
        },
        {
            "property_code": "product_code",
            "property_name": "产品编码",
            "data_type": "VARCHAR",
            "is_required": True,
            "ext_property": {
                "property_role_rule": {"property_role": "DIMENSION", "rule_type": "id"}
            },
        },
        {
            "property_code": "category",
            "property_name": "产品分类",
            "data_type": "VARCHAR",
            "is_required": False,
            "ext_property": {
                "property_role_rule": {"property_role": "DIMENSION", "rule_type": "name"}
            },
        },
        {
            "property_code": "price",
            "property_name": "价格",
            "data_type": "DECIMAL",
            "is_required": False,
            "ext_property": {
                "property_role_rule": {"property_role": "MEASURE", "rule_type": "raw_number"}
            },
        },
        {
            "property_code": "stock",
            "property_name": "库存数量",
            "data_type": "INTEGER",
            "is_required": False,
            "ext_property": {
                "property_role_rule": {"property_role": "MEASURE", "rule_type": "raw_number"}
            },
        },
        {
            "property_code": "description",
            "property_name": "产品描述",
            "data_type": "TEXT",
            "is_required": False,
            "ext_property": {
                "property_role_rule": {"property_role": "DIMENSION", "rule_type": "description"}
            },
        },
    ],
}

ObjectOwlBuilder, pack_to_zip, validate_object, chinese_to_entity_code = _load_sdk()

obj = data
if not obj.get("entity_code"):
    obj["entity_code"] = chinese_to_entity_code(obj["entity_name"])

obj.setdefault("entity_source", "DB")
obj.setdefault("datasource", datasource())
obj.setdefault("relations", [])
obj.setdefault("actions", [])

# 注入 id 主键
obj["fields"].insert(
    0,
    {
        "property_code": "id",
        "property_name": "主键",
        "data_type": "BIGINT",
        "is_required": True,
        "ext_property": {
            "property_role_rule": {"property_role": "MEASURE", "rule_type": "primary_key"}
        },
    },
)

print(
    json.dumps(
        {"ok": True, "entity_code": obj["entity_code"], "fields": len(obj["fields"])},
        ensure_ascii=False,
    )
)

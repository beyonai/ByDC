import json
import sys

data = {
  "entity_name": "产品信息",
  "entity_desc": "产品主数据",
  "fields": [
    {"property_code": "product_name", "property_name": "产品名称", "data_type": "VARCHAR", "is_required": True, "ext_property": {"property_role_rule": {"property_role": "DIMENSION", "rule_type": "name"}}},
    {"property_code": "product_code", "property_name": "产品编码", "data_type": "VARCHAR", "is_required": True, "ext_property": {"property_role_rule": {"property_role": "DIMENSION", "rule_type": "id"}}},
    {"property_code": "category", "property_name": "产品分类", "data_type": "VARCHAR", "is_required": False, "ext_property": {"property_role_rule": {"property_role": "DIMENSION", "rule_type": "name"}}},
    {"property_code": "price", "property_name": "价格", "data_type": "DECIMAL", "is_required": False, "ext_property": {"property_role_rule": {"property_role": "MEASURE", "rule_type": "raw_number"}}},
    {"property_code": "stock", "property_name": "库存数量", "data_type": "INTEGER", "is_required": False, "ext_property": {"property_role_rule": {"property_role": "MEASURE", "rule_type": "raw_number"}}},
    {"property_code": "description", "property_name": "产品描述", "data_type": "TEXT", "is_required": False, "ext_property": {"property_role_rule": {"property_role": "DIMENSION", "rule_type": "description"}}}
  ]
}

with open("product.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("done")

#!/usr/bin/env python3
"""
创建本体对象

用法:
    python create_object.py <object_json>
    python create_object.py --dry-run <object_json>

object_json 格式（JSON 字符串或文件路径）:
    {
        "entity_name": "客户信息",
        "entity_desc": "CRM 客户主数据",
        "fields": [
            {
                "property_code": "customer_name",
                "property_name": "客户名称",
                "data_type": "VARCHAR",
                "is_required": true,
                "ext_property": {
                    "property_role_rule": {"property_role": "DIMENSION", "rule_type": "name"}
                }
            }
        ],
        "relations": [],
        "actions": []
    }

执行步骤:
    1. 校验 JSON
    2. 自动生成 entity_code（中文转拼音）
    3. 注入 id 主键字段和 datasource 配置
    4. 生成 OWL 文件集（含 actions/）
    5. 打包 zip
    6. 上传 OWL 到 BYAI
    7. 在 SQLite 中建表
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# 把 lib 目录加入 path
sys.path.insert(0, str(Path(__file__).parent))

from lib.api_client import OntologyApiClient
from lib.sqlite_client import SqliteApiClient

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


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


def _datasource() -> dict:
    return {
        "db_code": "personal_sqlite",
        "db_type": "PERSONAL_SQLITE",
        "db_params": {
            "endpoint_url": "{{SQLITE_API_URL}}",
            "user_code": "{{USER_CODE}}",
        },
    }


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]

    if not args:
        print(__doc__)
        sys.exit(1)

    # 支持 JSON 字符串或文件路径
    raw = args[0]
    if Path(raw).exists():
        obj = json.loads(Path(raw).read_text(encoding="utf-8"))
    else:
        obj = json.loads(raw)

    ObjectOwlBuilder, pack_to_zip, validate_object, chinese_to_entity_code = _load_sdk()

    # 生成 entity_code
    if not obj.get("entity_code"):
        obj["entity_code"] = chinese_to_entity_code(obj["entity_name"])

    obj.setdefault("entity_source", "DB")
    obj.setdefault("fields", [])
    obj.setdefault("actions", [])
    obj.setdefault("relations", [])
    obj["datasource"] = _datasource()

    # 自动注入 id 主键
    if not any(f["property_code"] == "id" for f in obj["fields"]):
        obj["fields"].insert(
            0,
            {
                "property_code": "id",
                "property_name": "主键",
                "data_type": "BIGINT",
                "is_required": True,
                "source_column": "id",
                "property_group": "STORAGE",
                "ext_property": {
                    "property_role_rule": {"property_role": "MEASURE", "rule_type": "primary_key"}
                },
            },
        )

    # 校验
    result = validate_object(obj)
    if not result.ok:
        print(json.dumps({"ok": False, "error": result.to_text()}), flush=True)
        sys.exit(1)
    if result.warnings:
        for w in result.warnings:
            logger.warning("[警告] %s: %s", w.field, w.message)

    if dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "entity_code": obj["entity_code"],
                    "entity_name": obj["entity_name"],
                    "field_count": len(obj["fields"]),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return

    # 生成 OWL → zip
    owl_files = ObjectOwlBuilder().build(obj)
    zip_path = pack_to_zip(owl_files, entity_code=obj["entity_code"])

    # 上传 OWL
    api = OntologyApiClient()
    upload_result = api.upload_object(zip_path)

    # 建表
    sqlite = SqliteApiClient()
    sqlite.create_table_from_object(obj)

    print(
        json.dumps(
            {
                "ok": True,
                "entity_code": obj["entity_code"],
                "entity_name": obj["entity_name"],
                "resourceId": upload_result.get("resourceId"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

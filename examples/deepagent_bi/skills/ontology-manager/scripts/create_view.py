#!/usr/bin/env python3
"""
创建本体视图

用法:
    python create_view.py <view_json>
    python create_view.py --dry-run <view_json>

view_json 格式:
    {
        "view_name": "客户分析视图",
        "description": "用于分析客户数据的视图",
        "object_codes": ["by_customer", "by_opportunity"],
        "relations": [
            {
                "relation_code": "rel_scene_xxx_to_by_customer",
                "source_code": "scene_xxx",
                "target_code": "by_customer",
                "relation_type": "HAS_OBJECT",
                "joinkeys": []
            }
        ],
        "fields": [
            {
                "property_code": "customer_name",
                "property_name": "客户名称",
                "source_object": "by_customer",
                "source_property": "customer_name",
                "synonyms": ["客户"],
                "ext_property": {
                    "property_role_rule": {"property_role": "DIMENSION", "rule_type": "name"}
                }
            }
        ]
    }

注意:
    - 视图不创建 SQLite 表
    - view_code 自动从 view_name 生成（中文转拼音，前缀 scene_）
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.api_client import OntologyApiClient

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _load_sdk():
    try:
        from datacloud_data_sdk.ontology.owl_builder import ViewOwlBuilder
        from datacloud_data_sdk.ontology.owl_packager import pack_to_zip
        from datacloud_data_sdk.ontology.schema_validator import validate_view
        from datacloud_data_sdk.ontology.utils import chinese_to_entity_code

        return ViewOwlBuilder, pack_to_zip, validate_view, chinese_to_entity_code
    except ImportError as e:
        print(json.dumps({"ok": False, "error": f"SDK 未安装: {e}"}), flush=True)
        sys.exit(1)


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]

    if not args:
        print(__doc__)
        sys.exit(1)

    raw = args[0]
    if Path(raw).exists():
        view = json.loads(Path(raw).read_text(encoding="utf-8"))
    else:
        view = json.loads(raw)

    ViewOwlBuilder, pack_to_zip, validate_view, chinese_to_entity_code = _load_sdk()

    # 生成 view_code
    if not view.get("view_code"):
        view["view_code"] = chinese_to_entity_code(view["view_name"], prefix="scene_")

    view.setdefault("object_codes", [])
    view.setdefault("relations", [])
    view.setdefault("fields", [])

    # 校验
    result = validate_view(view)
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
                    "view_code": view["view_code"],
                    "view_name": view["view_name"],
                    "field_count": len(view["fields"]),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return

    owl_files = ViewOwlBuilder().build(view)
    zip_path = pack_to_zip(owl_files, entity_code=view["view_code"], is_view=True)

    api = OntologyApiClient()
    upload_result = api.upload_view(zip_path)

    print(
        json.dumps(
            {
                "ok": True,
                "view_code": view["view_code"],
                "view_name": view["view_name"],
                "resourceId": upload_result.get("resourceId"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
修改本体视图（替换字段列表）

用法:
    python modify_view.py <resource_id> <changes_json>
    python modify_view.py --dry-run <resource_id> <changes_json>

changes_json 格式:
    {
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
    - 视图修改不操作 SQLite
    - fields 为全量替换（不是增量）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.api_client import OntologyApiClient


def _load_sdk():
    try:
        from datacloud_data_sdk.ontology.owl_builder import ViewOwlBuilder
        from datacloud_data_sdk.ontology.owl_packager import pack_to_zip

        return ViewOwlBuilder, pack_to_zip
    except ImportError as e:
        print(json.dumps({"ok": False, "error": f"SDK 未安装: {e}"}), flush=True)
        sys.exit(1)


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]

    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    resource_id = args[0]
    raw = args[1]
    if Path(raw).exists():
        changes = json.loads(Path(raw).read_text(encoding="utf-8"))
    else:
        changes = json.loads(raw)

    ViewOwlBuilder, pack_to_zip = _load_sdk()

    api = OntologyApiClient()
    detail = api.get_detail(resource_id)
    view_code = detail.get("resourceCode", "")
    if not view_code:
        print(json.dumps({"ok": False, "error": f"资源 {resource_id} 不存在"}), flush=True)
        sys.exit(1)

    # 构建 view 对象（从 detail 恢复基本信息）
    view = {
        "view_code": view_code,
        "view_name": detail.get("resourceName", view_code),
        "description": detail.get("resourceDesc", ""),
        "object_codes": [],
        "relations": [],
        "fields": changes.get("fields", []),
    }

    if dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "view_code": view_code,
                    "field_count": len(view["fields"]),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return

    owl_files = ViewOwlBuilder().build(view)
    zip_path = pack_to_zip(owl_files, entity_code=view_code, is_view=True)
    api.upload_view(zip_path)

    print(
        json.dumps(
            {
                "ok": True,
                "view_code": view_code,
                "field_count": len(view["fields"]),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

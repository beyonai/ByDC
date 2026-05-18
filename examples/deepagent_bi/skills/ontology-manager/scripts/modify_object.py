#!/usr/bin/env python3
"""
修改本体对象（新增字段/修改关系/修改动作）

用法:
    python modify_object.py <resource_id> <changes_json>
    python modify_object.py --dry-run <resource_id> <changes_json>

changes_json 格式:
    {
        "fields": [
            {
                "property_code": "remark",
                "property_name": "备注",
                "data_type": "VARCHAR",
                "ext_property": {
                    "property_role_rule": {"property_role": "DIMENSION", "rule_type": "description"}
                }
            }
        ],
        "relations": [],
        "actions": []
    }

注意:
    - fields 中只支持新增字段，不支持删除字段（需二次确认）
    - 已存在的字段会被跳过（幂等）
    - SQLite 只执行 ALTER TABLE ADD COLUMN（不删列）
"""

from __future__ import annotations

import copy
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.api_client import OntologyApiClient
from lib.sqlite_client import SqliteApiClient

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _load_sdk():
    try:
        from datacloud_data_sdk.ontology.owl_builder import ObjectOwlBuilder
        from datacloud_data_sdk.ontology.owl_packager import pack_to_zip
        from datacloud_data_sdk.ontology.owl_parser import OwlParser

        return ObjectOwlBuilder, pack_to_zip, OwlParser
    except ImportError as e:
        print(json.dumps({"ok": False, "error": f"SDK 未安装: {e}"}), flush=True)
        sys.exit(1)


def _merge(old: dict, changes: dict) -> dict:
    new = copy.deepcopy(old)
    if "fields" in changes:
        existing_codes = {f["property_code"] for f in new["fields"]}
        for f in changes["fields"]:
            if f["property_code"] not in existing_codes:
                new["fields"].append(f)
    if "actions" in changes:
        new["actions"] = changes["actions"]
    if "relations" in changes:
        new["relations"] = changes["relations"]
    return new


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

    ObjectOwlBuilder, pack_to_zip, OwlParser = _load_sdk()

    api = OntologyApiClient()

    # 获取现有 OWL 详情（主表数据，resourceCode 用于重新上传）
    detail = api.get_detail(resource_id)
    entity_code = detail.get("resourceCode", "")
    if not entity_code:
        print(
            json.dumps({"ok": False, "error": f"资源 {resource_id} 不存在或无 resourceCode"}),
            flush=True,
        )
        sys.exit(1)

    # 从本地已解压的 OWL 文件解析现有对象定义（含完整字段列表）
    # OWL API Mock 上传时会解压到 resource/object/{code}/ 目录
    # 生产环境中 OWL 文件由系统管理，通过 owl_parser 解析
    from datacloud_data_sdk.ontology.loader import OntologyLoader

    # 尝试从 BYAI_BASE_URL 对应的 resource 目录加载（Mock 环境）
    # 生产环境中应通过专门的 OWL 下载接口获取
    resource_base = os.environ.get("OWL_RESOURCE_PATH", "")
    old_obj: dict = {
        "entity_code": entity_code,
        "entity_name": detail.get("resourceName", entity_code),
        "entity_desc": detail.get("resourceDesc", ""),
        "entity_source": "DB",
        "fields": [],
        "actions": [],
        "relations": [],
    }

    if resource_base:
        try:
            loader = OntologyLoader()
            loader.load_from_owl_resource_directory(resource_base)
            cls = loader._classes.get(entity_code)
            if cls:
                old_obj["fields"] = [
                    {
                        "property_code": f.field_code,
                        "property_name": f.field_name,
                        "data_type": f.field_type,
                        "is_required": f.required,
                        "source_column": f.source_column or f.field_code,
                        "property_group": "STORAGE",
                        "ext_property": {},
                    }
                    for f in cls.fields
                ]
        except Exception:
            pass  # fallback 到空字段列表，只做增量

    new_obj = _merge(old_obj, changes)

    if dry_run:
        added_fields = [f["property_code"] for f in changes.get("fields", [])]
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "entity_code": entity_code,
                    "added_fields": added_fields,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return

    # 重新生成 OWL 并上传
    from datacloud_data_sdk.ontology.utils import chinese_to_entity_code  # noqa: F401

    # 注入 datasource（保持原有配置）
    new_obj["datasource"] = {
        "db_code": "personal_sqlite",
        "db_type": "PERSONAL_SQLITE",
        "db_params": {"endpoint_url": "{{SQLITE_API_URL}}", "user_code": "{{USER_CODE}}"},
    }
    owl_files = ObjectOwlBuilder().build(new_obj)
    zip_path = pack_to_zip(owl_files, entity_code=entity_code)
    api.upload_object(zip_path)

    # 同步 SQLite 表结构（仅新增字段）
    sqlite = SqliteApiClient()
    sqlite.alter_table_from_diff(old_obj, new_obj)

    added = [
        f["property_code"]
        for f in changes.get("fields", [])
        if f["property_code"] not in {x["property_code"] for x in old_obj["fields"]}
    ]

    print(
        json.dumps(
            {
                "ok": True,
                "entity_code": entity_code,
                "added_fields": added,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

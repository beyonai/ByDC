#!/usr/bin/env python3
"""
删除本体对象（同时删除 OWL 和 SQLite 表）

用法:
    python delete_object.py <resource_id> <entity_code>
    python delete_object.py --dry-run <resource_id> <entity_code>

警告:
    此操作不可逆！将同时删除：
    - OWL 本体定义（软删，resourceStatus=3）
    - SQLite 中对应的数据表（DROP TABLE）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.api_client import OntologyApiClient
from lib.sqlite_client import SqliteApiClient


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]

    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    resource_id = args[0]
    entity_code = args[1]

    if dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "resource_id": resource_id,
                    "entity_code": entity_code,
                    "warning": "此操作将删除 OWL 定义和 SQLite 表，不可逆",
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return

    api = OntologyApiClient()
    api.delete_resource(resource_id)

    sqlite = SqliteApiClient()
    sqlite.drop_table(entity_code)

    print(
        json.dumps(
            {
                "ok": True,
                "resource_id": resource_id,
                "entity_code": entity_code,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

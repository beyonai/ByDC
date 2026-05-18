#!/usr/bin/env python3
"""
删除本体视图

用法:
    python delete_view.py <resource_id>
    python delete_view.py --dry-run <resource_id>

注意:
    - 视图删除不操作 SQLite
    - 软删（resourceStatus=3），数据可回查
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.api_client import OntologyApiClient


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]

    if not args:
        print(__doc__)
        sys.exit(1)

    resource_id = args[0]

    if dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "resource_id": resource_id,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return

    api = OntologyApiClient()
    api.delete_resource(resource_id)

    print(
        json.dumps(
            {
                "ok": True,
                "resource_id": resource_id,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

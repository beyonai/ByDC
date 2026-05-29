#!/usr/bin/env python3
"""查询个人/企业本体对象或视图列表。

I/O 协议：stdin JSON → stdout JSON

入参（stdin JSON，可选）:
    {
        "resource_biz_type": "",          # "OBJECT" / "VIEW" / ""(默认两个都有)
        "keyword": "",                   # 名称关键词过滤，默认空
        "owner_type": ""                 # "personal" / "enterprise" / ""(查全部)，默认 ""
    }

出参（stdout JSON）:
    {
        "ok": true,
        "data": [
            {
                "resourceId": "10000044",
                "resourceCode": "by_task",
                "resourceName": "任务管理对象"
            }
        ]
    }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from _common import post_json


def main() -> None:
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    params: dict = json.loads(raw) if raw else {}
    resource_biz_type: str = params.get("resource_biz_type", "").upper().strip()
    keyword: str = params.get("keyword", "")
    owner_type: str = params.get("owner_type", "").strip().lower()

    biz_types: list[str] = [resource_biz_type] if resource_biz_type else ["OBJECT", "VIEW"]

    payload: dict[str, Any] = {
        "keyword": keyword,
        "pageNum": 1,
        "pageSize": 100,
        "resourceStatus": "2",
        "resourceBizTypeList": biz_types,
        "permission": "",
        "language": "zh-CN",
    }
    if owner_type:
        payload["ownerType"] = owner_type

    data = post_json(
        path="/byaiService/auth/privilegeGrant/listResourceUseAuth",
        payload=payload,
    )
    items = (data or {}).get("list", [])
    result = [
        {
            "resourceId": item.get("resourceId"),
            "resourceCode": item.get("resourceCode"),
            "resourceName": item.get("resourceName"),
        }
        for item in items
    ]
    print(json.dumps({"ok": True, "data": result}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
        sys.exit(1)

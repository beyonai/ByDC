#!/usr/bin/env python3
"""
查询本体资源列表（对象或视图）

用法:
    python list_resources.py [--type OBJECT|VIEW] [--keyword 关键词]

参数:
    --type     资源类型，OBJECT（默认）或 VIEW
    --keyword  名称关键词过滤

输出示例:
    {
        "ok": true,
        "total": 3,
        "data": [
            {"resourceId": "10000018", "resourceCode": "by_customer", "resourceName": "客户信息表"},
            ...
        ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.api_client import OntologyApiClient


def main() -> None:
    parser = argparse.ArgumentParser(description="查询本体资源列表")
    parser.add_argument(
        "--type", dest="biz_type", default="OBJECT", choices=["OBJECT", "VIEW"], help="资源类型"
    )
    parser.add_argument("--keyword", default="", help="名称关键词过滤")
    args = parser.parse_args()

    api = OntologyApiClient()
    resources = api.list_resources(biz_type=args.biz_type)

    # 关键词过滤
    if args.keyword:
        kw = args.keyword.lower()
        resources = [
            r
            for r in resources
            if kw in r.get("resourceName", "").lower() or kw in r.get("resourceCode", "").lower()
        ]

    # 只返回关键字段
    data = [
        {
            "resourceId": r.get("resourceId"),
            "resourceCode": r.get("resourceCode"),
            "resourceName": r.get("resourceName"),
            "resourceDesc": r.get("resourceDesc", ""),
            "ownerType": r.get("ownerType"),
            "createTime": r.get("createTime"),
        }
        for r in resources
    ]

    print(
        json.dumps(
            {
                "ok": True,
                "biz_type": args.biz_type,
                "total": len(data),
                "data": data,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

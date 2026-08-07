"""e2e 骨架：非结构化对象实例发现接口（discoverObjectInstancesUnstructured）。

调用形态验证脚本：解析 base_id / instance_id / object_codes → 构造 RPC 调用
（POST /api/v1/rpc/search/discoverObjectInstancesUnstructured）→ 打印响应。

本版预期：已有实例发现（③）/ 新实例 LLM 抽取（④）为 TODO 占位，接口返回
501 not_implemented；⑤⑥⑦⑧（创建/登记/提及关系）为已实现能力，待③④接入后
由编排串联，本脚本的正向断言同步补齐。

用法：
    uv run python scripts/e2e_discover_object_instances_unstructured.py \
        --base-id BYCLAW_DATACLOUD \
        --instance-id <term_id> \
        --object-codes Methodology Concept
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from typing import Any

_DEFAULT_RPC_URL = "http://localhost:8088/api/v1/rpc/search/discoverObjectInstancesUnstructured"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="非结构化对象实例发现接口 e2e 骨架（本版预期 501 not_implemented）",
    )
    parser.add_argument(
        "--url",
        default=_DEFAULT_RPC_URL,
        help=f"RPC 端点地址（默认 {_DEFAULT_RPC_URL}）",
    )
    parser.add_argument("--base-id", default="BYCLAW_DATACLOUD", help="本体库 ID")
    parser.add_argument("--instance-id", required=True, help="输入实例 term_id")
    parser.add_argument(
        "--object-codes",
        nargs="+",
        required=True,
        help="非结构化对象类型编码列表（已有实例匹配范围 + 新实例候选类型）",
    )
    parser.add_argument(
        "--session-id",
        default="e2e-session",
        help="会话 ID（透传 X-Session-Id 请求头）",
    )
    return parser.parse_args(argv)


def _call_rpc(url: str, payload: dict[str, Any], session_id: str) -> dict[str, Any]:
    """构造 RPC 调用并返回响应 JSON。"""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Session-Id": session_id,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload: dict[str, Any] = {
        "params": {
            "base_id": args.base_id,
            "instance_id": args.instance_id,
            "object_codes": args.object_codes,
        }
    }
    print(f"POST {args.url}")
    print(f"payload: {json.dumps(payload, ensure_ascii=False)}")
    try:
        body = _call_rpc(args.url, payload, args.session_id)
    except urllib.error.URLError as exc:
        print(f"RPC 调用失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(body, ensure_ascii=False, indent=2))
    # 本版占位断言：③ 已有实例发现 TODO → 501 not_implemented
    if body.get("code") == 501 and "not implemented" in body.get("message", ""):
        print(
            "预期结果：501 not_implemented（③/④ TODO 占位短路，符合本版状态）",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

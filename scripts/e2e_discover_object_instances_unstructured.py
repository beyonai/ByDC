"""e2e：非结构化对象实例发现接口（discoverObjectInstancesUnstructured）全链路验证。

解析 base_id / instance_id / object_codes → 构造 RPC 调用
（POST /api/v1/rpc/search/discoverObjectInstancesUnstructured）→ 逐次记录指标并汇总。

本版：501 占位语义已移除；词典锚定（快路命中 + 反查兜底）+ LLM 抽取（优先类型枚举
+ 允许自动发现）已接入主流程。响应 items 中：已有实例（is_new=false，evidence=mention 原文片段）
在前、新实例（is_new=true）在后。

指标口径：
- temp=0 不可复现 → 默认多次运行（--runs，默认 3），输出均值±方差，不以单次为凭
- 金标泄漏隔离：输入实例 KB 文件须为全新未入库文本（录入时保证），
  不得用已入库实例的 KB 文件既抽取又比对
- 单篇延迟：单次调用耗时，上限 ~10s（超限标记 FAIL）

用法：
    uv run python scripts/e2e_discover_object_instances_unstructured.py \
        --base-id BYCLAW_DATACLOUD \
        --instance-id <term_id> \
        --object-codes Methodology Concept

退出码：0=全部断言通过；1=调用失败或断言失败。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Any

_DEFAULT_RPC_URL = "http://localhost:8088/api/v1/rpc/search/discoverObjectInstancesUnstructured"
_DEFAULT_RUNS = 3
_ELAPSED_LIMIT_SECONDS = 10.0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="非结构化对象实例发现接口 e2e（正向断言 + 指标汇总）",
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
        "--runs",
        type=int,
        default=_DEFAULT_RUNS,
        help=f"运行次数（temp=0 不可复现，取均值±方差；默认 {_DEFAULT_RUNS}）",
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


def _summarize(body: dict[str, Any]) -> dict[str, float | int]:
    """从响应提取指标：总数 / 已有命中数 / 新实例创建数。"""
    items = body.get("data", {}).get("items", [])
    total = len(items)
    hit_count = sum(1 for it in items if not it.get("is_new"))
    new_count = sum(1 for it in items if it.get("is_new"))
    return {"total": total, "hit_count": hit_count, "new_count": new_count}


def _assert_invariants(body: dict[str, Any]) -> list[str]:
    """正向断言：200 / 已有在前新在后 / evidence 语义。失败项以 'FAIL:' 开头。"""
    failures: list[str] = []
    if body.get("code") != 200:
        failures.append(f"FAIL: code={body.get('code')} 期望 200（501 已移除）")
        return failures
    items = body.get("data", {}).get("items", [])
    if not isinstance(items, list):
        failures.append("FAIL: data.items 非数组")
        return failures
    seen_new = False
    for it in items:
        if it.get("is_new"):
            seen_new = True
        elif seen_new:
            failures.append("FAIL: 已有实例（is_new=false）必须在前，发现新实例后又出现已有")
        if it.get("is_new") is True and it.get("evidence") is not None:
            failures.append(f"FAIL: 新实例 evidence 应为 None，实际 {it['evidence']!r}")
        if it.get("is_new") is False and not it.get("instance_id"):
            failures.append("FAIL: 已有实例缺 instance_id")
    return failures


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
    print(f"runs: {args.runs}（temp=0 不可复现 → 均值±方差口径）")

    metrics: list[dict[str, float | int]] = []
    elapsed_list: list[float] = []
    failures: list[str] = []
    for i in range(args.runs):
        started = time.monotonic()
        try:
            body = _call_rpc(args.url, payload, args.session_id)
        except urllib.error.URLError as exc:
            print(f"run {i + 1}: RPC 调用失败: {exc}", file=sys.stderr)
            return 1
        elapsed = time.monotonic() - started
        elapsed_list.append(elapsed)
        summary = _summarize(body)
        metrics.append(summary)
        if elapsed > _ELAPSED_LIMIT_SECONDS:
            failures.append(
                f"FAIL: run {i + 1} 延迟 {elapsed:.2f}s 超过上限 {_ELAPSED_LIMIT_SECONDS}s"
            )
        failures.extend(_assert_invariants(body))
        print(
            f"run {i + 1}: elapsed={elapsed:.2f}s total={summary['total']} "
            f"hit={summary['hit_count']} new={summary['new_count']}"
        )

    totals = [m["total"] for m in metrics]
    hits = [m["hit_count"] for m in metrics]
    news = [m["new_count"] for m in metrics]

    def _stat(values: list[float | int]) -> str:
        mean = statistics.mean(values)
        if len(values) > 1:
            return f"{mean:.2f} ± {statistics.stdev(values):.2f}"
        return f"{mean:.2f}（单次）"

    print("\n=== 指标汇总（均值 ± 标准差）===")
    print(f"items 总数:   {_stat(totals)}")
    print(f"已有命中数:   {_stat(hits)}")
    print(f"新实例创建数: {_stat(news)}")
    print(f"单篇延迟(s):  {_stat(elapsed_list)}（上限 {_ELAPSED_LIMIT_SECONDS}s）")
    print("=== 断言结果 ===")
    if failures:
        for f in failures:
            print(f)
        return 1
    print("PASS：code=200、已有在前新在后、新实例 evidence=None、单篇延迟达标")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

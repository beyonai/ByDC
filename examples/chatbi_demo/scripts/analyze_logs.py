#!/usr/bin/env python3
# ruff: noqa: T201, RUF001, RUF002, RUF003
"""日志分析与报告生成工具。

用法：
    # 生成单次运行的报告
    uv run python scripts/analyze_logs.py report \\
        --run-id run_20260522_001 \\
        --model ali-bailian/deepseek-v4-pro

    # 对比两次运行（调优前后）
    uv run python scripts/analyze_logs.py compare \\
        --model ali-bailian/deepseek-v4-pro \\
        --run-ids run_20260522_001,run_20260522_002

    # 输出失败 case 明细（用于调优分析）
    uv run python scripts/analyze_logs.py failures \\
        --run-id run_20260522_001 \\
        --model ali-bailian/deepseek-v4-pro \\
        --error-type field_mapping_error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
LOGS_DIR = REPO_ROOT / "logs"
REPORTS_DIR = REPO_ROOT / "reports"


def _model_slug(model: str) -> str:
    return model.replace("/", "_").replace(":", "_")


def _load_summary(run_id: str, model: str) -> dict:
    slug = _model_slug(model)
    f = LOGS_DIR / run_id / slug / "summary.json"
    if not f.exists():
        print(f"[ERROR] 找不到 summary: {f}", file=sys.stderr)
        sys.exit(1)
    return json.loads(f.read_text(encoding="utf-8"))


def _load_cases(run_id: str, model: str) -> list[dict]:
    slug = _model_slug(model)
    cases_dir = LOGS_DIR / run_id / slug / "cases"
    if not cases_dir.exists():
        return []
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(cases_dir.glob("*.json"))]


def _render_report(summary: dict, cases: list[dict], compare_summary: dict | None = None) -> str:
    model = summary["model"]
    run_id = summary["run_id"]
    accuracy = summary["accuracy"]
    passed = summary["passed"]
    total = summary["total"]
    patch_ver = summary.get("prompt_patch_version", "v1")
    perf = summary.get("perf", {})

    lines = [
        "# 评测报告",
        "",
        f"**模型**: `{model}`  ",
        f"**Run ID**: `{run_id}`  ",
        f"**Prompt Patch**: `{patch_ver}`  ",
        f"**评测时间**: {summary.get('started_at', '-')}  ",
        "",
        "---",
        "",
        "## 总体准确率",
        "",
    ]

    # 与上轮对比
    if compare_summary:
        prev_acc = compare_summary["accuracy"]
        delta = accuracy - prev_acc
        delta_str = f"+{delta:.1%}" if delta >= 0 else f"{delta:.1%}"
        lines.append("| 指标 | 本轮 | 上轮 | 变化 |")
        lines.append("|------|------|------|------|")
        lines.append(f"| 准确率 | **{accuracy:.1%}** | {prev_acc:.1%} | {delta_str} |")
        lines.append(f"| 通过数 | {passed}/{total} | {compare_summary['passed']}/{compare_summary['total']} | - |")
    else:
        lines.append(f"**{accuracy:.1%}**（{passed}/{total} 通过）")

    lines += [
        "",
        "---",
        "",
        "## 分类准确率",
        "",
        "| 分类 | 通过 | 总数 | 准确率 |",
        "|------|------|------|--------|",
    ]
    for cat, v in sorted(summary.get("by_category", ).items()):
        bar = "█" * int(v["accuracy"] * 10) + "░" * (10 - int(v["accuracy"] * 10))
        lines.append(f"| {cat} | {v['passed']} | {v['total']} | {v['accuracy']:.1%} {bar} |")

    lines += [
        "",
        "---",
        "",
        "## 性能指标",
        "",
        "| 指标 | 值 | 说明 |",
        "|------|-----|------|",
        f"| 平均总耗时 | {perf.get('avg_total_duration_ms', 0)}ms | 端到端 |",
        f"| P50 耗时 | {perf.get('p50_total_duration_ms', 0)}ms | 中位数 |",
        f"| P95 耗时 | {perf.get('p95_total_duration_ms', 0)}ms | 长尾 |",
        f"| 平均首字节 | {perf.get('avg_ttft_ms', 0)}ms | TTFT |",
        f"| 平均 ReAct 轮次 | {perf.get('avg_react_turns', 0)} | 推理链长度 |",
        f"| 最大 ReAct 轮次 | {perf.get('max_react_turns', 0)} | |",
        f"| 平均思考速度 | {perf.get('avg_thinking_chars_per_sec', 0):.1f} 字/秒 | 目标 ≥ 20 |",
        f"| 最低思考速度 | {perf.get('min_thinking_chars_per_sec', 0):.1f} 字/秒 | |",
        f"| 思考速度 < 20 字/秒 | {perf.get('cases_below_20chars_per_sec', 0)} 条 | 需关注 |",
        "",
        "---",
        "",
        "## 错误分布",
        "",
    ]

    error_dist = summary.get("error_distribution", {})
    if error_dist:
        lines.append("| 错误类型 | 数量 | 调优方向 |")
        lines.append("|---------|------|---------|")
        tuning_map = {
            "field_mapping_error": "本体 synonyms/property_name 调整",
            "join_logic_error": "SDK JOIN 逻辑或 prompt 调整",
            "aggregation_error": "prompt patch 补充聚合说明",
            "syntax_error": "prompt patch 补充 SQL 格式说明",
            "timeout": "SDK 超时配置或 prompt 精简",
            "other": "人工分析",
        }
        for err_type, cnt in sorted(error_dist.items(), key=lambda x: -x[1]):
            direction = tuning_map.get(err_type, "-")
            lines.append(f"| `{err_type}` | {cnt} | {direction} |")
    else:
        lines.append("无失败 case。")

    # 失败 case 明细（前 10 条）
    failed = [c for c in cases if not c.get("passed")]
    if failed:
        lines += [
            "",
            "---",
            "",
            f"## 失败 Case 明细（前 {min(10, len(failed))} 条）",
            "",
        ]
        for c in failed[:10]:
            perf_c = c.get("perf", {})
            lines += [
                f"### {c['case_id']} — `{c.get('error_type', 'unknown')}`",
                "",
                f"**问题**: {c['question']}  ",
                f"**视图**: `{c['view_code']}`  ",
                f"**分类**: {c.get('category')} / {c.get('difficulty')}  ",
                f"**耗时**: {perf_c.get('total_duration_ms', '-')}ms  ReAct={perf_c.get('react_turns', '-')}  思考速度={perf_c.get('thinking_chars_per_sec', '-')} 字/秒  ",
                "",
                "**生成 SQL**:",
                "```sql",
                f"{c.get('generated_sql') or '（无输出）'}",
                "```",
                "",
                "**期望 SQL**:",
                "```sql",
                f"{c.get('expected_sql', '')}",
                "```",
                "",
            ]

    lines += [
        "---",
        "",
        "*报告由 analyze_logs.py 自动生成*",
    ]
    return "\n".join(lines)


def cmd_report(args: argparse.Namespace) -> None:
    summary = _load_summary(args.run_id, args.model)
    cases = _load_cases(args.run_id, args.model)

    report_md = _render_report(summary, cases)

    slug = _model_slug(args.model)
    out_dir = REPORTS_DIR / slug / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "report.md"
    out_file.write_text(report_md, encoding="utf-8")
    print(f"报告已生成: {out_file}")
    print(f"准确率: {summary['accuracy']:.1%} ({summary['passed']}/{summary['total']})")


def cmd_compare(args: argparse.Namespace) -> None:
    run_ids = args.run_ids.split(",")
    if len(run_ids) < 2:
        print("[ERROR] 需要至少两个 run_id", file=sys.stderr)
        sys.exit(1)

    summaries = [_load_summary(rid, args.model) for rid in run_ids]
    cases_latest = _load_cases(run_ids[-1], args.model)

    report_md = _render_report(summaries[-1], cases_latest, compare_summary=summaries[-2])

    slug = _model_slug(args.model)
    out_dir = REPORTS_DIR / slug / run_ids[-1]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "report_compare.md"
    out_file.write_text(report_md, encoding="utf-8")
    print(f"对比报告已生成: {out_file}")

    # 打印简要对比
    print(f"\n{'Run ID':<30} {'准确率':>8} {'通过':>6} {'总数':>6}")
    print("-" * 55)
    for s in summaries:
        print(f"{s['run_id']:<30} {s['accuracy']:>7.1%} {s['passed']:>6} {s['total']:>6}")


def cmd_failures(args: argparse.Namespace) -> None:
    cases = _load_cases(args.run_id, args.model)
    failed = [c for c in cases if not c.get("passed")]

    if args.error_type:
        failed = [c for c in failed if c.get("error_type") == args.error_type]

    print(f"失败 case 共 {len(failed)} 条（error_type={args.error_type or '全部'}）\n")
    for c in failed:
        perf_c = c.get("perf", {})
        print(f"[{c['case_id']}] {c.get('error_type')} | {c['question']}")
        print(f"  耗时={perf_c.get('total_duration_ms')}ms  ReAct={perf_c.get('react_turns')}  思考={perf_c.get('thinking_chars_per_sec')} 字/秒")
        print(f"  生成: {(c.get('generated_sql') or '无')[:120]}")
        print(f"  期望: {c.get('expected_sql', '')[:120]}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="日志分析与报告生成")
    sub = parser.add_subparsers(dest="cmd")

    p_report = sub.add_parser("report", help="生成单次运行报告")
    p_report.add_argument("--run-id", required=True)
    p_report.add_argument("--model", required=True)

    p_compare = sub.add_parser("compare", help="对比两次运行")
    p_compare.add_argument("--model", required=True)
    p_compare.add_argument("--run-ids", required=True, help="逗号分隔的 run_id，如 run_001,run_002")

    p_fail = sub.add_parser("failures", help="输出失败 case 明细")
    p_fail.add_argument("--run-id", required=True)
    p_fail.add_argument("--model", required=True)
    p_fail.add_argument("--error-type", default=None)

    args = parser.parse_args()
    if args.cmd == "report":
        cmd_report(args)
    elif args.cmd == "compare":
        cmd_compare(args)
    elif args.cmd == "failures":
        cmd_failures(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

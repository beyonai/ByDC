"""批量测试 llm_confirm 语义化输出效果。

从 llm_confirm_test_cases.json 加载测试用例，逐条调用 llm_confirm，
输出语义化确认视图和 SQL 还原结果，并对照 expected_checks 做基础断言。

用法：
    uv run packages/datacloud-knowledge/scripts/manual/run_llm_confirm_batch.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from datacloud_knowledge.intent.llm_confirm import (
    ConfirmedQuery,
    llm_confirm,
    semantic_to_display,
    semantic_to_sql_expr,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

CASES_FILE = Path(__file__).parent / "llm_confirm_test_cases.json"


def _print_confirmed_view(confirmed: ConfirmedQuery) -> None:
    """打印用户确认视图。"""
    print("\n  查询值:")
    for s in confirmed.select:
        display = semantic_to_display(s)
        sql = semantic_to_sql_expr(s)
        print(f"    {s.original_keyword}: {display}")
        print(f"      → SQL: {sql}")
        if s.filters:
            for f in s.filters:
                val = ", ".join(f.value) if isinstance(f.value, list) else str(f.value)
                print(f"      限定: {f.dimension} {f.op} {val}")

    if confirmed.group_by:
        print("\n  分组:")
        for g in confirmed.group_by:
            print(f"    {g.original_keyword or g.field} → {g.field}")

    if confirmed.where:
        print("\n  过滤:")
        for w in confirmed.where:
            kw = w.original_field_keyword or w.original_value_keyword or w.field
            print(f"    {kw} → {w.field} {w.op} {w.value}")

    if confirmed.order_by:
        print("\n  排序:")
        for o in confirmed.order_by:
            print(f"    {o.original_keyword or o.field} → {o.field} {o.direction}")

    if confirmed.clarify_items:
        print("\n  ⚠️ 需确认:")
        for ci in confirmed.clarify_items:
            src = f"[{ci.source}] " if ci.source else ""
            print(f"    {src}{ci.keyword} → {' / '.join(ci.candidates)}")
            if ci.reason:
                print(f"      原因: {ci.reason}")


def _check_expectations(
    confirmed: ConfirmedQuery,
    checks: dict[str, Any],
    case_name: str,
) -> list[str]:
    """对照 expected_checks 做基础断言，返回失败消息列表。"""
    failures: list[str] = []

    # select_count
    if "select_count" in checks:
        expected = checks["select_count"]
        actual = len(confirmed.select)
        if actual != expected:
            failures.append(f"select_count: 期望 {expected}, 实际 {actual}")

    # has_filter_dimension: 检查 select 中的 filters 是否包含指定维度
    if "has_filter_dimension" in checks:
        all_filter_dims: set[str] = set()
        for s in confirmed.select:
            for f in s.filters:
                all_filter_dims.add(f.dimension)
        for dim in checks["has_filter_dimension"]:
            if dim not in all_filter_dims:
                failures.append(f"has_filter_dimension: 缺少维度 '{dim}'，实际: {all_filter_dims}")

    # has_agg_func: 检查 select 中是否包含指定聚合函数
    if "has_agg_func" in checks:
        all_agg_funcs = {s.agg_func.upper() for s in confirmed.select if s.agg_func}
        for func in checks["has_agg_func"]:
            if func not in all_agg_funcs:
                failures.append(f"has_agg_func: 缺少 '{func}'，实际: {all_agg_funcs}")

    # no_filters: 检查 select 中是否无 filters
    if checks.get("no_filters"):
        for s in confirmed.select:
            if s.filters:
                failures.append(
                    f"no_filters: '{s.original_keyword}' 不应有 filters，"
                    f"实际: {[f.dimension for f in s.filters]}"
                )

    # has_where_field: 检查 WHERE 中是否包含指定字段
    if "has_where_field" in checks:
        all_where_fields = {w.field for w in confirmed.where}
        for field in checks["has_where_field"]:
            if field not in all_where_fields:
                failures.append(f"has_where_field: 缺少 '{field}'，实际: {all_where_fields}")

    return failures


def run_batch() -> None:
    """加载测试用例并逐条执行。"""
    if not CASES_FILE.exists():
        print(f"测试用例文件不存在: {CASES_FILE}")
        sys.exit(1)

    cases: list[dict[str, Any]] = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    total = len(cases)
    passed = 0
    failed = 0
    errors = 0

    print(f"{'=' * 70}")
    print(f"llm_confirm 批量测试 — 共 {total} 个用例")
    print(f"{'=' * 70}")

    for i, case in enumerate(cases, start=1):
        name = case["name"]
        desc = case.get("description", "")
        print(f"\n{'─' * 70}")
        print(f"[{i}/{total}] {name}")
        print(f"  描述: {desc}")
        print(f"  查询: {case['original_question']}")

        try:
            confirmed = llm_confirm(
                original_question=case["original_question"],
                expanded_query=case["expanded_query"],
                recall_context=case["recall_context"],
            )
        except Exception:
            logger.exception("LLM 调用异常")
            print("  ❌ LLM 调用异常")
            errors += 1
            continue

        if confirmed is None:
            print("  ❌ LLM 返回 None")
            errors += 1
            continue

        _print_confirmed_view(confirmed)

        # 检查 expectations
        checks = case.get("expected_checks", {})
        failures = _check_expectations(confirmed, checks, name)

        if failures:
            failed += 1
            print(f"\n  ❌ 断言失败 ({len(failures)} 项):")
            for msg in failures:
                print(f"    - {msg}")
        else:
            passed += 1
            print("\n  ✅ 通过")

    # 汇总
    print(f"\n{'=' * 70}")
    print(f"汇总: {total} 用例, ✅ {passed} 通过, ❌ {failed} 失败, 💥 {errors} 异常")
    print(f"{'=' * 70}")

    if failed > 0 or errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_batch()

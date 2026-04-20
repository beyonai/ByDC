"""批量评估召回质量 — 对测试集中每条 case 重跑 extract + recall，对比新旧召回结果。

读取 llm_confirm_test_cases.json，逐条执行：
  1. extract_terms（从 structured_input 提取术语）
  2. _unified_recall（执行召回）
  3. format_recall_context（格式化）
  4. 对比新旧 recall_context 的候选差异

支持 --save-results 保存新的 recall_context 到 JSON，
可用于替换测试集中的 recall_context 后重跑 confirm eval。

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/eval_clarify_recall.py
    uv run python packages/datacloud-knowledge/scripts/manual/eval_clarify_recall.py --cases 0,2,6
    uv run python packages/datacloud-knowledge/scripts/manual/eval_clarify_recall.py --save-results /tmp/new_recall.json
"""

from dotenv import load_dotenv

load_dotenv()

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TEST_CASES_FILE = Path(__file__).parent / "llm_confirm_test_cases.json"

# 从 recall_context 文本中提取候选列表的正则
_CANDIDATE_RE = re.compile(r"^\s+(.+?)\s+\((\w+)\):\s+\[(.+)\]$", re.MULTILINE)


def _parse_recall_context(ctx: str) -> dict[str, list[str]]:
    """从 recall_context 文本中提取 {ktype:keyword -> [候选名]} 映射。"""
    result: dict[str, list[str]] = {}
    for m in _CANDIDATE_RE.finditer(ctx):
        keyword = m.group(1).strip()
        ktype = m.group(2).strip()
        candidates_str = m.group(3)
        candidates = [c.strip().strip("'\"") for c in candidates_str.split(",")]
        key = f"{ktype}:{keyword}"
        result[key] = candidates
    return result


def _run_recall_for_case(case: dict[str, Any]) -> tuple[str, list[Any], dict[str, Any]]:
    """对单条 case 执行 extract + recall，返回 (recall_context, terms, recall_map)。"""
    from datacloud_knowledge.intent.clarification.api import _unified_recall
    from datacloud_knowledge.intent.clarification.confirm import format_recall_context
    from datacloud_knowledge.intent.clarification.extract import (
        extract_terms_complex_conditions,
        extract_terms_compute,
        extract_terms_query,
    )

    structured_input = case["structured_input"]
    mode = case["mode"]
    complex_conditions: list[str] = structured_input.get("complex_conditions") or []

    # Step 1: extract
    if mode == "query":
        main_terms = extract_terms_query(structured_input)
    else:
        main_terms = extract_terms_compute(structured_input)

    cc_terms = extract_terms_complex_conditions(complex_conditions) if complex_conditions else []
    all_terms = main_terms + cc_terms

    # Step 2: recall
    recall_map = _unified_recall(all_terms)

    # Step 3: format
    recall_context = format_recall_context(
        all_terms,
        recall_map,
        complex_conditions=complex_conditions,
    )

    return recall_context, all_terms, recall_map


def _compare_recall(
    old_ctx: str,
    new_ctx: str,
) -> dict[str, Any]:
    """对比新旧 recall_context 的候选差异。"""
    old_parsed = _parse_recall_context(old_ctx)
    new_parsed = _parse_recall_context(new_ctx)

    all_keys = sorted(set(old_parsed) | set(new_parsed))
    diffs: list[dict[str, Any]] = []
    improved = 0
    degraded = 0
    unchanged = 0

    for key in all_keys:
        old_cands = old_parsed.get(key, [])
        new_cands = new_parsed.get(key, [])

        if old_cands == new_cands:
            unchanged += 1
            continue

        removed = [c for c in old_cands if c not in new_cands]
        added = [c for c in new_cands if c not in old_cands]

        diff_entry: dict[str, Any] = {"key": key}
        if removed:
            diff_entry["removed"] = removed
        if added:
            diff_entry["added"] = added
        diff_entry["old_top3"] = old_cands[:3]
        diff_entry["new_top3"] = new_cands[:3]
        diffs.append(diff_entry)

    # 新增的 key（之前没有召回结果，现在有了）
    new_keys = set(new_parsed) - set(old_parsed)
    old_keys = set(old_parsed) - set(new_parsed)

    return {
        "diffs": diffs,
        "unchanged": unchanged,
        "new_keys": sorted(new_keys),
        "lost_keys": sorted(old_keys),
        "improved": improved,
        "degraded": degraded,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="评估召回质量")
    parser.add_argument("--cases", type=str, default=None, help="逗号分隔的 case 索引")
    parser.add_argument("--save-results", type=str, default=None, help="保存新 recall 结果到 JSON")
    parser.add_argument(
        "--update-test-cases",
        action="store_true",
        help="用新的 recall_context 更新测试集 JSON（原地修改）",
    )
    args = parser.parse_args()

    if not TEST_CASES_FILE.exists():
        print(f"测试集不存在: {TEST_CASES_FILE}")
        sys.exit(1)

    cases: list[dict[str, Any]] = json.loads(TEST_CASES_FILE.read_text("utf-8"))
    print(f"加载测试集: {len(cases)} 条\n")

    indices = list(range(len(cases)))
    if args.cases:
        indices = [int(x.strip()) for x in args.cases.split(",")]

    saved: list[dict[str, Any]] = []
    total_diffs = 0
    total_new_keys = 0
    total_lost_keys = 0

    for idx in indices:
        if idx >= len(cases):
            print(f"[{idx}] 超出范围，跳过")
            continue

        case = cases[idx]
        query = case["query"]
        mode = case["mode"]
        old_recall_ctx = case["recall_context"]

        print(f"{'=' * 70}")
        print(f"[Case {idx}] {query[:60]}")
        print(f"  mode={mode}")

        # 执行新召回
        new_recall_ctx, terms, recall_map = _run_recall_for_case(case)

        # 打印术语提取结果
        enabled_terms = [t for t in terms if t.search_enabled]
        vector_only_terms = [t for t in terms if t.vector_only]
        skipped_terms = [t for t in terms if not t.search_enabled]
        print(
            f"  术语: {len(terms)} 总 | {len(enabled_terms)} 召回 | "
            f"{len(vector_only_terms)} 向量only | {len(skipped_terms)} 跳过"
        )

        if vector_only_terms:
            for t in vector_only_terms:
                cands = recall_map.get(f"{t.ktype}:{t.raw_text}", [])
                top = [c["term_name"] for c in cands[:3]] if cands else []
                print(f"    vector_only: {t.ktype}:{t.raw_text} -> {top}")

        if skipped_terms:
            for t in skipped_terms:
                print(f"    skipped: {t.ktype}:{t.raw_text}")

        # 对比
        report = _compare_recall(old_recall_ctx, new_recall_ctx)
        n_diffs = len(report["diffs"])
        total_diffs += n_diffs
        total_new_keys += len(report["new_keys"])
        total_lost_keys += len(report["lost_keys"])

        if n_diffs == 0 and not report["new_keys"] and not report["lost_keys"]:
            print("  ✓ 召回结果无变化")
        else:
            if report["new_keys"]:
                print(f"  + 新增召回 ({len(report['new_keys'])}):")
                for k in report["new_keys"]:
                    new_cands = _parse_recall_context(new_recall_ctx).get(k, [])
                    print(f"    {k}: {new_cands[:3]}")

            if report["lost_keys"]:
                print(f"  - 丢失召回 ({len(report['lost_keys'])}):")
                for k in report["lost_keys"]:
                    old_cands = _parse_recall_context(old_recall_ctx).get(k, [])
                    print(f"    {k}: {old_cands[:3]}")

            if report["diffs"]:
                print(f"  ~ 候选变化 ({n_diffs}):")
                for d in report["diffs"]:
                    print(f"    {d['key']}:")
                    if d.get("removed"):
                        print(f"      removed: {d['removed']}")
                    if d.get("added"):
                        print(f"      added:   {d['added']}")
                    print(f"      old_top3: {d['old_top3']}")
                    print(f"      new_top3: {d['new_top3']}")

        # 保存
        saved.append(
            {
                "case": idx,
                "query": query,
                "mode": mode,
                "recall_context": new_recall_ctx,
                "terms_count": len(terms),
                "enabled_count": len(enabled_terms),
                "vector_only_count": len(vector_only_terms),
            }
        )

        # 更新测试集
        if args.update_test_cases:
            cases[idx]["recall_context"] = new_recall_ctx

        print()

    # 汇总
    print("=" * 70)
    print("汇总")
    print("=" * 70)
    print(f"  总 case:      {len(indices)}")
    print(f"  候选变化:     {total_diffs}")
    print(f"  新增召回 key: {total_new_keys}")
    print(f"  丢失召回 key: {total_lost_keys}")

    if args.save_results and saved:
        out_path = Path(args.save_results)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\n  结果已保存: {out_path}")

    if args.update_test_cases:
        TEST_CASES_FILE.write_text(
            json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\n  测试集已更新: {TEST_CASES_FILE}")


if __name__ == "__main__":
    main()

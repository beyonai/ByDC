"""评估 confirm 模块准确率 — 读取采集的测试集，修改 prompt 后重跑 LLM，对比结果。

读取 llm_confirm_test_cases.json，逐条调用 llm_confirm_structured，
对比新结果与原始结果的字段映射准确率。

支持：
  - 替换 CONFIRM_SYSTEM_PROMPT 测试不同 prompt 策略
  - 按 case index 过滤（--cases 0,3,7）
  - 输出逐条对比报告 + 汇总统计

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/eval_clarify_confirm.py
    uv run python packages/datacloud-knowledge/scripts/manual/eval_clarify_confirm.py --cases 0,3
"""

from dotenv import load_dotenv

load_dotenv()

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

# ── 可替换的 System Prompt（修改这里测试不同策略）─────────────────────

CUSTOM_SYSTEM_PROMPT: str | None = None
"""设为 None 使用生产 CONFIRM_SYSTEM_PROMPT；设为字符串则替换。"""

# ── 测试集路径 ───────────────────────────────────────────────────────

TEST_CASES_FILE = Path(__file__).parent / "llm_confirm_test_cases.json"


# ── 对比逻辑 ─────────────────────────────────────────────────────────


def _extract_field_mappings(
    structured_input: dict[str, Any],
    result: dict[str, Any],
    mode: str,
) -> list[dict[str, str]]:
    """提取 input→output 的字段映射对，用于逐项对比。

    返回 [{"slot": "select.0", "input": "企业全称", "output": "企业全称"}, ...]
    """
    mappings: list[dict[str, str]] = []

    if mode == "query":
        # select
        in_select = structured_input.get("select") or []
        out_select = result.get("select") or []
        for i, (inp, out) in enumerate(zip(in_select, out_select, strict=False)):
            mappings.append({"slot": f"select.{i}", "input": str(inp), "output": str(out)})

        # filters[].field
        in_filters = structured_input.get("filters") or []
        out_filters = result.get("filters") or []
        for i, (inf, outf) in enumerate(zip(in_filters, out_filters, strict=False)):
            if isinstance(inf, dict) and isinstance(outf, dict):
                mappings.append(
                    {
                        "slot": f"filters.{i}.field",
                        "input": str(inf.get("field", "")),
                        "output": str(outf.get("field", "")),
                    }
                )

        # order_by[].field
        in_ob = structured_input.get("order_by") or []
        out_ob = result.get("order_by") or []
        for i, (ino, outo) in enumerate(zip(in_ob, out_ob, strict=False)):
            if isinstance(ino, dict) and isinstance(outo, dict):
                mappings.append(
                    {
                        "slot": f"order_by.{i}.field",
                        "input": str(ino.get("field", "")),
                        "output": str(outo.get("field", "")),
                    }
                )

    else:  # compute
        # dimensions[].field
        in_dims = structured_input.get("dimensions") or []
        out_dims = result.get("dimensions") or []
        for i, (ind, outd) in enumerate(zip(in_dims, out_dims, strict=False)):
            inp_f = ind.get("field", str(ind)) if isinstance(ind, dict) else str(ind)
            out_f = outd.get("field", str(outd)) if isinstance(outd, dict) else str(outd)
            mappings.append({"slot": f"dimensions.{i}", "input": inp_f, "output": out_f})

        # metrics[].field
        in_metrics = structured_input.get("metrics") or []
        out_metrics = result.get("metrics") or []
        for i, (inm, outm) in enumerate(zip(in_metrics, out_metrics, strict=False)):
            if isinstance(inm, dict) and isinstance(outm, dict):
                mappings.append(
                    {
                        "slot": f"metrics.{i}.field",
                        "input": str(inm.get("field", "")),
                        "output": str(outm.get("field", "")),
                    }
                )

        # filters[].field
        in_filters = structured_input.get("filters") or []
        out_filters = result.get("filters") or []
        for i, (inf, outf) in enumerate(zip(in_filters, out_filters, strict=False)):
            if isinstance(inf, dict) and isinstance(outf, dict):
                mappings.append(
                    {
                        "slot": f"filters.{i}.field",
                        "input": str(inf.get("field", "")),
                        "output": str(outf.get("field", "")),
                    }
                )

        # order_by[].field
        in_ob = structured_input.get("order_by") or []
        out_ob = result.get("order_by") or []
        for i, (ino, outo) in enumerate(zip(in_ob, out_ob, strict=False)):
            if isinstance(ino, dict) and isinstance(outo, dict):
                mappings.append(
                    {
                        "slot": f"order_by.{i}.field",
                        "input": str(ino.get("field", "")),
                        "output": str(outo.get("field", "")),
                    }
                )

    return mappings


def _compare_results(
    baseline: dict[str, Any] | None,
    new_result: dict[str, Any] | None,
    structured_input: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    """对比 baseline 和 new_result，返回差异报告。"""
    report: dict[str, Any] = {
        "baseline_ok": baseline is not None,
        "new_ok": new_result is not None,
        "field_diffs": [],
        "clarify_diff": {},
        "needs_clarification_match": None,
    }

    if baseline is None or new_result is None:
        return report

    # needs_clarification
    report["needs_clarification_match"] = baseline.get("needs_clarification") == new_result.get(
        "needs_clarification"
    )

    # 字段映射对比
    base_maps = _extract_field_mappings(structured_input, baseline, mode)
    new_maps = _extract_field_mappings(structured_input, new_result, mode)

    base_by_slot = {m["slot"]: m["output"] for m in base_maps}
    new_by_slot = {m["slot"]: m["output"] for m in new_maps}

    all_slots = sorted(set(base_by_slot) | set(new_by_slot))
    for slot in all_slots:
        b = base_by_slot.get(slot, "<missing>")
        n = new_by_slot.get(slot, "<missing>")
        if b != n:
            report["field_diffs"].append({"slot": slot, "baseline": b, "new": n})

    # clarify_items 对比
    base_clarify = {ci["keyword"] for ci in baseline.get("clarify_items", [])}
    new_clarify = {ci["keyword"] for ci in new_result.get("clarify_items", [])}
    report["clarify_diff"] = {
        "only_baseline": sorted(base_clarify - new_clarify),
        "only_new": sorted(new_clarify - base_clarify),
        "common": sorted(base_clarify & new_clarify),
    }

    return report


def _check_fabrication(
    result: dict[str, Any],
    recall_context: str,
) -> list[str]:
    """检查 clarify_items.candidates 是否存在编造（不在 recall_context 中的字段名）。"""
    violations: list[str] = []
    for ci in result.get("clarify_items", []):
        for cand in ci.get("candidates", []):
            if cand and cand not in recall_context:
                violations.append(f"  clarify[{ci['keyword']}]: 候选 '{cand}' 不在召回结果中")
    return violations


# ── 主流程 ───────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="评估 confirm 模块准确率")
    parser.add_argument(
        "--cases",
        type=str,
        default=None,
        help="逗号分隔的 case 索引，如 0,3,7。默认跑全部。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只对比已有 baseline，不调用 LLM。",
    )
    parser.add_argument(
        "--save-results",
        type=str,
        default=None,
        help="将每条 case 的 new result 保存到指定 JSON 文件。",
    )
    args = parser.parse_args()

    if not TEST_CASES_FILE.exists():
        print(f"测试集不存在: {TEST_CASES_FILE}")
        sys.exit(1)

    cases: list[dict[str, Any]] = json.loads(TEST_CASES_FILE.read_text("utf-8"))
    print(f"加载测试集: {len(cases)} 条\n")

    # 过滤 case
    indices = list(range(len(cases)))
    if args.cases:
        indices = [int(x.strip()) for x in args.cases.split(",")]

    # 替换 prompt（如果指定了自定义 prompt）
    if CUSTOM_SYSTEM_PROMPT and not args.dry_run:
        import datacloud_knowledge.intent.clarification.confirm as confirm_mod

        confirm_mod.CONFIRM_SYSTEM_PROMPT = CUSTOM_SYSTEM_PROMPT
        print(">>> 使用自定义 CONFIRM_SYSTEM_PROMPT\n")

    # 统计
    total = 0
    llm_ok = 0
    llm_fail = 0
    field_match = 0
    field_total = 0
    clarify_match = 0
    fabrication_cases = 0
    needs_clarification_match = 0
    saved_results: list[dict[str, Any]] = []

    for idx in indices:
        if idx >= len(cases):
            print(f"[{idx}] 超出范围，跳过")
            continue

        case = cases[idx]
        query = case["query"]
        structured_input = case["structured_input"]
        recall_context = case["recall_context"]
        mode = case["mode"]
        baseline = case.get("result")
        total += 1

        print(f"{'=' * 70}")
        print(f"[Case {idx}] {query[:60]}")
        print(f"  mode={mode} | baseline={'OK' if baseline else 'FAIL'}")

        if args.dry_run:
            # 只分析 baseline
            if baseline is None:
                llm_fail += 1
                print("  baseline=null，跳过\n")
                continue
            llm_ok += 1
            maps = _extract_field_mappings(structured_input, baseline, mode)
            field_total += len(maps)
            field_match += len(maps)  # baseline 自身无法对比，全算 match
            fabs = _check_fabrication(baseline, recall_context)
            if fabs:
                fabrication_cases += 1
                print("  ⚠ 编造候选:")
                for f in fabs:
                    print(f"    {f}")
            print(
                f"  字段映射 {len(maps)} 项 | clarify {len(baseline.get('clarify_items', []))} 项"
            )
            print()
            continue

        # 调用 LLM（禁用数据采集，避免污染测试集）
        import datacloud_knowledge.intent.clarification.confirm as _confirm_mod
        from datacloud_knowledge.intent.clarification.confirm import llm_confirm_structured

        _confirm_mod._save_test_case = lambda *_a, **_kw: None  # type: ignore[assignment]

        print("  调用 LLM...", end=" ", flush=True)
        new_result_obj = llm_confirm_structured(
            query=query,
            structured_input=structured_input,
            recall_context=recall_context,
            mode=mode,
        )

        if new_result_obj is None:
            llm_fail += 1
            print("FAIL")
            print()
            continue

        llm_ok += 1
        new_result = new_result_obj.model_dump()
        print("OK")

        # 保存结果
        saved_results.append({"case": idx, "query": query, "mode": mode, "result": new_result})

        # 对比（baseline 可能为 None）
        report = _compare_results(baseline, new_result, structured_input, mode)

        # 字段映射统计
        maps = _extract_field_mappings(structured_input, new_result, mode)
        field_total += len(maps)
        n_diffs = len(report["field_diffs"])
        field_match += len(maps) - n_diffs

        # needs_clarification
        if report["needs_clarification_match"]:
            needs_clarification_match += 1

        # clarify 对比
        cd = report.get("clarify_diff") or {}
        if cd and not cd.get("only_baseline") and not cd.get("only_new"):
            clarify_match += 1

        # 编造检查
        fabs = _check_fabrication(new_result, recall_context)
        if fabs:
            fabrication_cases += 1

        # 输出
        if n_diffs == 0 and not fabs:
            print("  ✓ 字段映射完全一致")
        else:
            if n_diffs:
                print(f"  ✗ 字段差异 ({n_diffs}):")
                for d in report["field_diffs"]:
                    print(f"    {d['slot']}: {d['baseline']} → {d['new']}")
            if fabs:
                print("  ⚠ 编造候选:")
                for f in fabs:
                    print(f"    {f}")

        nc_base = baseline.get("needs_clarification") if baseline else "N/A"
        nc_new = new_result.get("needs_clarification")
        print(f"  needs_clarification: baseline={nc_base} new={nc_new}")

        if cd.get("only_baseline"):
            print(f"  clarify 仅 baseline: {cd['only_baseline']}")
        if cd.get("only_new"):
            print(f"  clarify 仅 new: {cd['only_new']}")
        print()

    # ── 汇总 ─────────────────────────────────────────────────────────
    print("=" * 70)
    print("汇总统计")
    print("=" * 70)
    print(f"  总用例:           {total}")
    print(f"  LLM 成功:         {llm_ok}/{total} ({llm_ok / total * 100:.0f}%)" if total else "")
    print(f"  LLM 失败:         {llm_fail}")
    if field_total:
        print(
            f"  字段映射一致:     {field_match}/{field_total} ({field_match / field_total * 100:.0f}%)"
        )
    if not args.dry_run and llm_ok:
        print(f"  needs_clarification 一致: {needs_clarification_match}/{llm_ok}")
        print(f"  clarify_items 完全一致:   {clarify_match}/{llm_ok}")
    print(f"  存在编造候选:     {fabrication_cases} 条")

    # 保存完整结果
    if args.save_results and saved_results:
        out_path = Path(args.save_results)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(saved_results, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n  结果已保存: {out_path} ({len(saved_results)} 条)")


if __name__ == "__main__":
    main()

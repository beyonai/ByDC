#!/usr/bin/env python3
# ruff: noqa: RUF001, RUF002, RUF003, PLC0415, PLW2901, ASYNC109, DTZ005, RET504
"""评测执行脚本。

用法：
    # 单模型评测（并发分片，由 /quest worker 调用）
    uv run python scripts/run_eval.py \\
        --model ali-bailian/deepseek-v4-pro \\
        --run-id run_20260522_001 \\
        --workers 4 \\
        --concurrency 20

    # 指定 prompt patch 版本
    uv run python scripts/run_eval.py \\
        --model ali-bailian/qwen3.6-27b \\
        --prompt-patch eval/prompt_patches/qwen3.6-27b/v2.json \\
        --run-id run_20260522_002

    # 只跑指定分类
    uv run python scripts/run_eval.py \\
        --model ali-bailian/deepseek-v4-pro \\
        --categories join,complex \\
        --run-id run_20260522_003
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
import uuid
from collections import Counter
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent
EVAL_DIR = REPO_ROOT / "eval"
LOGS_DIR = REPO_ROOT / "logs"

# 默认超时（秒）
DEFAULT_TIMEOUT = int(os.environ.get("EVAL_TIMEOUT_SEC", "60"))
DEFAULT_RETRY = int(os.environ.get("EVAL_RETRY", "2"))


def _load_env(model_env_file: str | None = None) -> None:
    """加载环境变量：先读公共 .demo_env，再用 model_env 覆盖。"""
    base_env = REPO_ROOT / ".demo_env"
    if not base_env.exists():
        base_env = REPO_ROOT / ".demo_env_example"
    if base_env.exists():
        for line in base_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    # model env 覆盖（强制覆盖，不用 setdefault）
    if model_env_file:
        p = Path(model_env_file)
        if not p.is_absolute():
            p = REPO_ROOT / p
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()
            logger.info("加载 model env: %s", p)


def _load_prompt_patch(patch_path: str | None) -> dict:
    if not patch_path:
        return {}
    p = Path(patch_path)
    if not p.exists():
        logger.warning("prompt patch 文件不存在: %s，使用空 patch", patch_path)
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    logger.info("加载 prompt patch: %s v%s", data.get("model_id"), data.get("version"))
    return data


def _sql_match(generated: str, expected: str) -> bool:
    """简单 SQL 匹配：规范化后比较关键词和表名。"""
    def normalize(sql: str) -> str:
        import re
        sql = sql.upper().strip()
        sql = re.sub(r"\s+", " ", sql)
        sql = re.sub(r"\s*,\s*", ",", sql)
        return sql

    gen = normalize(generated)
    exp = normalize(expected)
    if gen == exp:
        return True

    # 宽松匹配：检查关键表名和聚合函数是否一致
    import re
    def extract_tables(sql: str) -> set[str]:
        return set(re.findall(r"(?:FROM|JOIN)\s+(\w+\.\w+|\w+)", sql.upper()))

    def extract_agg(sql: str) -> set[str]:
        return set(re.findall(r"(COUNT|SUM|AVG|MAX|MIN)\s*\(", sql.upper()))

    gen_tables = extract_tables(gen)
    exp_tables = extract_tables(exp)
    gen_agg = extract_agg(gen)
    exp_agg = extract_agg(exp)

    # 表名完全一致且聚合函数一致，视为通过
    return gen_tables == exp_tables and gen_agg == exp_agg


def _classify_error(generated_sql: str, expected_sql: str, error_detail: str) -> str:
    if not generated_sql:
        return "timeout"
    if "SyntaxError" in error_detail or "syntax error" in error_detail.lower():
        return "syntax_error"

    import re
    gen_up = generated_sql.upper()
    exp_up = expected_sql.upper()

    # 字段映射错误：生成的字段名和期望的不一致
    gen_fields = set(re.findall(r"\.(\w+)\b", gen_up))
    exp_fields = set(re.findall(r"\.(\w+)\b", exp_up))
    if exp_fields and len(gen_fields & exp_fields) / len(exp_fields) < 0.5:
        return "field_mapping_error"

    # JOIN 逻辑错误
    gen_joins = set(re.findall(r"JOIN\s+(\w+)", gen_up))
    exp_joins = set(re.findall(r"JOIN\s+(\w+)", exp_up))
    if exp_joins and gen_joins != exp_joins:
        return "join_logic_error"

    # 聚合错误
    gen_agg = set(re.findall(r"(COUNT|SUM|AVG|MAX|MIN)\s*\(", gen_up))
    exp_agg = set(re.findall(r"(COUNT|SUM|AVG|MAX|MIN)\s*\(", exp_up))
    if exp_agg and gen_agg != exp_agg:
        return "aggregation_error"

    return "other"


async def _run_single_case(
    agent: object,
    case: dict,
    semaphore: asyncio.Semaphore,
    log_dir: Path,
    timeout: int,
    retry: int,
) -> dict:
    """执行单个 case，采集性能指标，写入 cases/{case_id}.json。"""
    from datacloud_analysis import AnswerEvent, PerfEvent

    case_id = case["id"]
    question = case["question"]
    view_code = case["view_code"]

    for attempt in range(retry + 1):
        async with semaphore:
            t_start = time.monotonic()
            generated_sql = ""
            error_detail = ""
            perf_data: dict = {}

            try:
                async def _collect() -> tuple[str, dict]:
                    sql = ""
                    perf: dict = {}
                    async for event in agent.ask(  # type: ignore[attr-defined]
                        question=question,
                        view_codes=[view_code],
                        thread_id=str(uuid.uuid4()),
                        user_code="eval_user",
                    ):
                        if isinstance(event, AnswerEvent):
                            sql = event.content
                        elif isinstance(event, PerfEvent):
                            perf = {
                                "total_duration_ms": event.total_duration_ms,
                                "ttft_ms": event.ttft_ms,
                                "react_turns": event.react_turns,
                                "llm_call_count": event.llm_call_count,
                                "interrupt_count": event.interrupt_count,
                                "thinking_chars": event.thinking_chars,
                                "thinking_duration_ms": event.thinking_duration_ms,
                                "thinking_chars_per_sec": event.thinking_chars_per_sec,
                            }
                    return sql, perf

                generated_sql, perf_data = await asyncio.wait_for(_collect(), timeout=timeout)
            except TimeoutError:
                error_detail = "TimeoutError"
                logger.warning("case %s 超时（attempt %d/%d）", case_id, attempt + 1, retry + 1)
                if attempt < retry:
                    continue
            except Exception as exc:
                error_detail = str(exc)
                logger.warning("case %s 异常: %s（attempt %d/%d）", case_id, exc, attempt + 1, retry + 1)
                if attempt < retry:
                    continue

            # 如果没有 PerfEvent（旧版 SDK），用总耗时补充
            if not perf_data:
                perf_data = {
                    "total_duration_ms": int((time.monotonic() - t_start) * 1000),
                    "ttft_ms": None,
                    "react_turns": 0,
                    "llm_call_count": 0,
                    "interrupt_count": 0,
                    "thinking_chars": 0,
                    "thinking_duration_ms": 0,
                    "thinking_chars_per_sec": 0.0,
                }

            passed = bool(generated_sql) and _sql_match(generated_sql, case["expected_sql"])
            error_type = None if passed else _classify_error(generated_sql, case["expected_sql"], error_detail)

            result = {
                "case_id": case_id,
                "view_code": view_code,
                "question": question,
                "generated_sql": generated_sql,
                "expected_sql": case["expected_sql"],
                "category": case["category"],
                "difficulty": case["difficulty"],
                "passed": passed,
                "error_type": error_type,
                "error_detail": error_detail or None,
                "perf": perf_data,
            }

            # 写入单题日志
            case_file = log_dir / "cases" / f"{case_id}.json"
            case_file.parent.mkdir(parents=True, exist_ok=True)
            case_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

            status = "PASS" if passed else f"FAIL({error_type})"
            logger.info(
                "case %s [%s] %dms react=%d thinking=%.1f chars/s",
                case_id, status,
                perf_data.get("total_duration_ms", 0),
                perf_data.get("react_turns", 0),
                perf_data.get("thinking_chars_per_sec", 0.0),
            )
            return result

    return {"case_id": case_id, "passed": False, "error_type": "timeout", "perf": {}}


def _write_summary(
    log_dir: Path,
    model: str,
    patch_version: str,
    results: list[dict],
    started_at: str,
    duration_sec: float,
) -> None:
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))

    by_category: dict[str, dict] = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0}
        by_category[cat]["total"] += 1
        if r.get("passed"):
            by_category[cat]["passed"] += 1
    for v in by_category.values():
        v["accuracy"] = round(v["passed"] / v["total"], 3) if v["total"] else 0.0

    # 性能统计
    perfs = [r["perf"] for r in results if r.get("perf")]
    durations = [p["total_duration_ms"] for p in perfs if p.get("total_duration_ms")]
    ttfts = [p["ttft_ms"] for p in perfs if p.get("ttft_ms")]
    react_turns = [p["react_turns"] for p in perfs if p.get("react_turns") is not None]
    cps_list = [p["thinking_chars_per_sec"] for p in perfs if p.get("thinking_chars_per_sec")]

    def percentile(lst: list, p: int) -> float:
        if not lst:
            return 0.0
        s = sorted(lst)
        idx = int(len(s) * p / 100)
        return s[min(idx, len(s) - 1)]

    perf_summary = {
        "avg_total_duration_ms": int(sum(durations) / len(durations)) if durations else 0,
        "p50_total_duration_ms": int(percentile(durations, 50)),
        "p95_total_duration_ms": int(percentile(durations, 95)),
        "avg_ttft_ms": int(sum(ttfts) / len(ttfts)) if ttfts else 0,
        "avg_react_turns": round(sum(react_turns) / len(react_turns), 2) if react_turns else 0,
        "max_react_turns": max(react_turns) if react_turns else 0,
        "avg_thinking_chars_per_sec": round(sum(cps_list) / len(cps_list), 1) if cps_list else 0.0,
        "min_thinking_chars_per_sec": round(min(cps_list), 1) if cps_list else 0.0,
        "cases_below_20chars_per_sec": sum(1 for c in cps_list if c < 20),
    }

    error_dist = Counter(r.get("error_type") for r in results if not r.get("passed") and r.get("error_type"))

    summary = {
        "run_id": log_dir.parent.name,
        "model": model,
        "prompt_patch_version": patch_version,
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total, 3) if total else 0.0,
        "by_category": by_category,
        "error_distribution": dict(error_dist),
        "perf": perf_summary,
        "duration_sec": round(duration_sec, 1),
        "started_at": started_at,
    }

    summary_file = log_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "评测完成: %s 准确率=%.1f%% (%d/%d) 耗时=%.1fs",
        model, summary["accuracy"] * 100, passed, total, duration_sec,
    )


async def run_eval(
    model: str,
    run_id: str,
    eval_file: Path,
    patch_path: str | None,
    categories: list[str] | None,
    concurrency: int,
    timeout: int,
    retry: int,
    model_env_file: str | None = None,
) -> None:
    import datetime

    from datacloud_analysis import OntologyAgent, OntologyAgentConfig

    _load_env(model_env_file)
    patch = _load_prompt_patch(patch_path)
    patch_version = patch.get("version", "v1") if patch else "v1"

    # 加载评测集
    cases = []
    with eval_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                case = json.loads(line)
                if categories is None or case["category"] in categories:
                    cases.append(case)

    logger.info("加载 %d 条 case（模型=%s patch=%s）", len(cases), model, patch_version)

    # 日志目录
    model_slug = model.replace("/", "_").replace(":", "_")
    log_dir = LOGS_DIR / run_id / model_slug
    log_dir.mkdir(parents=True, exist_ok=True)

    # 构建 agent
    # kimi 系列模型只允许 temperature=1
    temperature = float(os.environ.get("DEMO_TEMPERATURE", "0.6"))
    if "kimi" in model.lower():
        temperature = 1.0

    config = OntologyAgentConfig(
        api_key=os.environ.get("DEMO_API_KEY", ""),
        base_url=os.environ.get("DEMO_BASE_URL", ""),
        model=model,
        temperature=temperature,
        resource_path=str(REPO_ROOT / os.environ.get("DEMO_RESOURCE_PATH", "resource")),
    )
    agent = OntologyAgent(config)

    semaphore = asyncio.Semaphore(concurrency)
    started_at = datetime.datetime.now().isoformat()
    t_start = time.monotonic()

    tasks = [
        _run_single_case(agent, case, semaphore, log_dir, timeout, retry)
        for case in cases
    ]
    results = await asyncio.gather(*tasks)

    duration_sec = time.monotonic() - t_start
    _write_summary(log_dir, model, patch_version, list(results), started_at, duration_sec)


def main() -> None:
    parser = argparse.ArgumentParser(description="评测执行脚本")
    parser.add_argument("--model", required=True, help="模型 ID，如 ali-bailian/deepseek-v4-pro")
    parser.add_argument("--run-id", required=True, help="本次运行 ID，如 run_20260522_001")
    parser.add_argument("--eval-file", default=str(EVAL_DIR / "cases.jsonl"), help="评测集路径")
    parser.add_argument("--prompt-patch", default=None, help="prompt patch 文件路径")
    parser.add_argument("--categories", default=None, help="逗号分隔的分类过滤，如 join,complex")
    parser.add_argument("--concurrency", type=int, default=20, help="case 并发数")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单 case 超时秒数")
    parser.add_argument("--retry", type=int, default=DEFAULT_RETRY, help="失败重试次数")

    args = parser.parse_args()
    categories = args.categories.split(",") if args.categories else None

    asyncio.run(run_eval(
        model=args.model,
        run_id=args.run_id,
        eval_file=Path(args.eval_file),
        patch_path=args.prompt_patch,
        categories=categories,
        concurrency=args.concurrency,
        timeout=args.timeout,
        retry=args.retry,
    ))


if __name__ == "__main__":
    main()

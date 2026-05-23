#!/usr/bin/env python3
# ruff: noqa: T201, RUF001, RUF002, RUF003
"""并发评测编排脚本：同时启动 6 个模型的评测进程。

用法：
    # 并发跑所有模型
    uv run python scripts/run_eval_all.py --run-id run_20260522_001

    # 只跑指定模型
    uv run python scripts/run_eval_all.py --run-id run_20260522_001 --models qwen3.6-27b,deepseek-v4-flash

    # 跑完后自动生成汇总报告
    uv run python scripts/run_eval_all.py --run-id run_20260522_001 --report
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent
MODEL_ENV_DIR = REPO_ROOT / "model_env"
LOGS_DIR = REPO_ROOT / "logs"

# .venv 在仓库根目录（chatbi_demo 往上两级）
_GIT_ROOT = REPO_ROOT.parent.parent
_VENV_PYTHON = _GIT_ROOT / ".venv" / "Scripts" / "python.exe"
if not _VENV_PYTHON.exists():
    _VENV_PYTHON = _GIT_ROOT / ".venv" / "bin" / "python"
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable

ALL_MODELS = [
    "qwen3.6-35b-a3b",
    "qwen3.6-27b",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "kimi-k2.6",
    "glm-5.1",
]


def _model_slug(model: str) -> str:
    return model.replace("/", "_").replace(":", "_")


def run_all(
    run_id: str,
    models: list[str],
    concurrency: int,
    timeout: int,
    categories: str | None,
    report: bool,
) -> None:
    procs: dict[str, subprocess.Popen] = {}
    start_times: dict[str, float] = {}

    print(f"\n{'='*60}")
    print(f"  并发评测启动  run_id={run_id}")
    print(f"  模型数: {len(models)}  case并发: {concurrency}  超时: {timeout}s")
    print(f"{'='*60}\n")

    # 并发启动所有模型进程
    for model in models:
        env_file = MODEL_ENV_DIR / f"{model}.env"
        if not env_file.exists():
            print(f"[WARN] 找不到 {env_file}，跳过 {model}")
            continue

        cmd = [
            PYTHON, str(SCRIPTS_DIR / "run_eval.py"),
            "--env-file", str(env_file),
            "--run-id", run_id,
            "--concurrency", str(concurrency),
            "--timeout", str(timeout),
        ]
        if categories:
            cmd += ["--categories", categories]

        log_file = LOGS_DIR / run_id / _model_slug(model) / "process.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        with log_file.open("w", encoding="utf-8") as lf:
            proc = subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=str(REPO_ROOT),
            )
        procs[model] = proc
        start_times[model] = time.monotonic()
        print(f"  [启动] {model:<25} pid={proc.pid}  日志: {log_file.relative_to(REPO_ROOT)}")

    if not procs:
        print("[ERROR] 没有可用的模型进程启动")
        sys.exit(1)

    print(f"\n  等待 {len(procs)} 个进程完成...\n")

    # 轮询等待所有进程结束
    done: set[str] = set()
    while len(done) < len(procs):
        for model, proc in procs.items():
            if model in done:
                continue
            ret = proc.poll()
            if ret is not None:
                elapsed = time.monotonic() - start_times[model]
                status = "OK" if ret == 0 else f"FAIL(exit={ret})"
                print(f"  [{status}] {model:<25} 耗时={elapsed:.0f}s")
                done.add(model)
        if len(done) < len(procs):
            time.sleep(3)

    print(f"\n{'='*60}")
    print(f"  全部完成  run_id={run_id}")
    print(f"{'='*60}\n")

    # 打印各模型准确率汇总
    _print_summary(run_id, models)

    # 生成报告
    if report:
        for model in models:
            summary_file = LOGS_DIR / run_id / _model_slug(model) / "summary.json"
            if not summary_file.exists():
                continue
            subprocess.run(
                [PYTHON, str(SCRIPTS_DIR / "analyze_logs.py"),
                 "report", "--run-id", run_id, "--model", model],
                cwd=str(REPO_ROOT),
                check=False,
            )


def _print_summary(run_id: str, models: list[str]) -> None:
    import json

    print(f"{'模型':<25} {'准确率':>8} {'通过':>6} {'总数':>6} {'平均耗时':>10} {'平均ReAct':>10}")
    print("-" * 75)
    for model in models:
        summary_file = LOGS_DIR / run_id / _model_slug(model) / "summary.json"
        if not summary_file.exists():
            print(f"{model:<25} {'N/A':>8}")
            continue
        s = json.loads(summary_file.read_text(encoding="utf-8"))
        perf = s.get("perf", {})
        print(
            f"{model:<25} {s['accuracy']:>7.1%} {s['passed']:>6} {s['total']:>6}"
            f" {perf.get('avg_total_duration_ms', 0):>8}ms {perf.get('avg_react_turns', 0):>9.1f}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="并发评测编排脚本")
    parser.add_argument("--run-id", required=True, help="本次运行 ID，如 run_20260522_001")
    parser.add_argument("--models", default=None,
                        help=f"逗号分隔的模型列表，默认全部: {','.join(ALL_MODELS)}")
    parser.add_argument("--concurrency", type=int, default=10, help="每个模型内部 case 并发数（默认10）")
    parser.add_argument("--timeout", type=int, default=60, help="单 case 超时秒数（默认60）")
    parser.add_argument("--categories", default=None, help="只跑指定分类，如 simple,aggregate")
    parser.add_argument("--report", action="store_true", help="完成后自动生成 markdown 报告")

    args = parser.parse_args()
    models = args.models.split(",") if args.models else ALL_MODELS

    run_all(
        run_id=args.run_id,
        models=models,
        concurrency=args.concurrency,
        timeout=args.timeout,
        categories=args.categories,
        report=args.report,
    )


if __name__ == "__main__":
    main()

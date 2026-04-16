"""G20 closeout regression runner and report rendering."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class RegressionCase:
    case_id: str
    category: str
    title: str
    command: str
    required: bool = True


@dataclass(frozen=True)
class RegressionResult:
    case_id: str
    category: str
    title: str
    command: str
    required: bool
    returncode: int
    duration_sec: float
    status: str
    output_preview: str


def build_default_cases() -> list[RegressionCase]:
    """Return the default G20 closeout regression matrix."""
    return [
        RegressionCase(
            case_id="C1",
            category="core",
            title="闲聊短路（不进图）",
            command=(
                "uv run pytest "
                "packages/datacloud-analysis/tests/dca/unit/test_worker_resume_regressions.py "
                "-k ask_chitchat_short_circuits_without_graph_execution -q"
            ),
        ),
        RegressionCase(
            case_id="C2",
            category="core",
            title="自动确权后可规划与执行",
            command=(
                "uv run pytest "
                "packages/datacloud-analysis/tests/dca/unit/test_planning_node.py "
                "packages/datacloud-analysis/tests/dca/unit/test_execution_node.py "
                "-k online_query_records_invocation_and_persists_todo_md -q"
            ),
        ),
        RegressionCase(
            case_id="C3",
            category="core",
            title="中断恢复链路（含 checkpoint 语义）",
            command=(
                "uv run pytest "
                "packages/datacloud-analysis/tests/dca/unit/test_worker_resume_regressions.py "
                "packages/datacloud-analysis/tests/dca/unit/test_execution_node.py "
                '-k "resume or level3_interrupt" -q'
            ),
        ),
        RegressionCase(
            case_id="C4",
            category="core",
            title="子 agent 委托路径（不被术语澄清阻断）",
            command=(
                "uv run pytest "
                "packages/datacloud-analysis/tests/dca/unit/test_planning_node.py "
                "-k agent_delegate_todo_injects_default_delegate_policy -q"
            ),
        ),
        RegressionCase(
            case_id="P1",
            category="stability",
            title="图主链结构稳定性",
            command=(
                "uv run pytest "
                "packages/datacloud-analysis/tests/dca/unit/test_graph_builder_pipeline.py -q"
            ),
        ),
        RegressionCase(
            case_id="P2",
            category="stability",
            title="Tool Hook 回调链稳定性",
            command=(
                "uv run pytest "
                "packages/datacloud-analysis/tests/dca/unit/test_tool_hook_plugin_manager.py -q"
            ),
        ),
        RegressionCase(
            case_id="P3",
            category="performance",
            title="关键单测集合时延基线（执行层）",
            command=(
                "uv run pytest packages/datacloud-analysis/tests/dca/unit/test_execution_node.py -q"
            ),
            required=False,
        ),
    ]


def _preview(text: str, *, limit: int = 800) -> str:
    content = text.strip()
    if len(content) <= limit:
        return content
    return f"{content[:limit]}...(truncated)"


def run_regression_cases(
    cases: list[RegressionCase],
    *,
    workdir: Path,
    dry_run: bool = False,
) -> list[RegressionResult]:
    """Execute regression cases and return structured results."""
    results: list[RegressionResult] = []
    for case in cases:
        if dry_run:
            results.append(
                RegressionResult(
                    case_id=case.case_id,
                    category=case.category,
                    title=case.title,
                    command=case.command,
                    required=case.required,
                    returncode=0,
                    duration_sec=0.0,
                    status="dry-run",
                    output_preview="dry-run: command not executed",
                )
            )
            continue

        started = time.perf_counter()
        completed = subprocess.run(  # noqa: S603
            case.command,
            cwd=str(workdir),
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
        duration = time.perf_counter() - started
        merged_output = "\n".join([completed.stdout, completed.stderr]).strip()
        status = "passed" if completed.returncode == 0 else "failed"
        results.append(
            RegressionResult(
                case_id=case.case_id,
                category=case.category,
                title=case.title,
                command=case.command,
                required=case.required,
                returncode=completed.returncode,
                duration_sec=duration,
                status=status,
                output_preview=_preview(merged_output),
            )
        )
    return results


def render_markdown_report(
    *,
    results: list[RegressionResult],
    generated_at: str,
    baseline_commit: str,
    target_commit: str,
) -> str:
    """Render markdown closeout report from results."""
    total = len(results)
    passed = sum(1 for item in results if item.status in {"passed", "dry-run"})
    failed_required = [item for item in results if item.required and item.status == "failed"]
    failed_optional = [item for item in results if not item.required and item.status == "failed"]
    overall = "PASS" if not failed_required else "FAIL"

    lines: list[str] = [
        "# G20 全链路回归报告",
        "",
        f"- 生成时间：{generated_at}",
        f"- 基线提交：`{baseline_commit}`",
        f"- 目标提交：`{target_commit}`",
        f"- 总用例数：{total}",
        f"- 通过数：{passed}",
        f"- 必测失败数：{len(failed_required)}",
        f"- 可选失败数：{len(failed_optional)}",
        f"- 结论：**{overall}**",
        "",
        "## 结果明细",
        "",
        "| Case | 类别 | 必测 | 结果 | 耗时(s) | 命令 |",
        "|---|---|---|---|---:|---|",
    ]
    for item in results:
        required_text = "Y" if item.required else "N"
        lines.append(
            f"| {item.case_id} | {item.category} | {required_text} | {item.status} | "
            f"{item.duration_sec:.2f} | `{item.command}` |"
        )

    lines.append("")
    lines.append("## 失败项")
    lines.append("")
    if not failed_required and not failed_optional:
        lines.append("- 无失败项。")
    else:
        for item in failed_required + failed_optional:
            must = "必测" if item.required else "可选"
            lines.append(f"- `{item.case_id}`（{must}）{item.title}")
            lines.append(f"  - returncode: `{item.returncode}`")
            if item.output_preview:
                lines.append("  - 输出摘录：")
                lines.append("")
                lines.append("```text")
                lines.append(item.output_preview)
                lines.append("```")

    lines.append("")
    lines.append("## 发布判定")
    lines.append("")
    if failed_required:
        lines.append("- 阻断发布：存在必测失败项，请先修复后重跑。")
    else:
        lines.append("- 可发布：必测项全部通过。")
        if failed_optional:
            lines.append("- 风险提示：存在可选失败项，需在发布记录中说明。")
    lines.append("")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run G20 closeout regression suite.")
    parser.add_argument(
        "--output",
        default=("docs/概要设计/重构剩余批次/04-收口波次D/G20-全链路回归与发布清单/回归报告.md"),
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--json-output",
        default=("docs/概要设计/重构剩余批次/04-收口波次D/G20-全链路回归与发布清单/回归结果.json"),
        help="JSON result output path.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not execute commands.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[5]
    output_path = (repo_root / args.output).resolve()
    json_path = (repo_root / args.json_output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    cases = build_default_cases()
    results = run_regression_cases(cases, workdir=repo_root, dry_run=bool(args.dry_run))

    head = (
        subprocess.run(  # noqa: S603
            "git rev-parse --short HEAD",
            cwd=str(repo_root),
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    ) or "unknown"
    report = render_markdown_report(
        results=results,
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        baseline_commit=head,
        target_commit=head,
    )
    output_path.write_text(report, encoding="utf-8")
    json_path.write_text(
        json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    required_failed = any(item.required and item.status == "failed" for item in results)
    return 1 if required_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

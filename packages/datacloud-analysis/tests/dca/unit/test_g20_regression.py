from __future__ import annotations

from pathlib import Path

from datacloud_analysis.release.g20_regression import (
    RegressionCase,
    RegressionResult,
    build_default_cases,
    render_markdown_report,
    run_regression_cases,
)


def test_build_default_cases_contains_required_core_scenarios() -> None:
    cases = build_default_cases()
    case_ids = {item.case_id for item in cases if item.category == "core"}
    assert {"C1", "C2", "C3", "C4"}.issubset(case_ids)
    assert all(item.command for item in cases)


def test_run_regression_cases_dry_run_marks_cases_without_execution() -> None:
    cases = [
        RegressionCase(
            case_id="T1",
            category="core",
            title="dry run check",
            command="echo should-not-run",
            required=True,
        )
    ]
    results = run_regression_cases(cases, workdir=Path.cwd(), dry_run=True)
    assert len(results) == 1
    assert results[0].status == "dry-run"
    assert results[0].returncode == 0


def test_render_markdown_report_outputs_fail_when_required_failed() -> None:
    results = [
        RegressionResult(
            case_id="C1",
            category="core",
            title="must pass",
            command="pytest x",
            required=True,
            returncode=1,
            duration_sec=1.2,
            status="failed",
            output_preview="traceback ...",
        ),
        RegressionResult(
            case_id="P1",
            category="performance",
            title="optional",
            command="pytest y",
            required=False,
            returncode=1,
            duration_sec=0.4,
            status="failed",
            output_preview="optional failed",
        ),
    ]
    report = render_markdown_report(
        results=results,
        generated_at="2026-03-31 12:00:00",
        baseline_commit="abc123",
        target_commit="def456",
    )
    assert "结论：**FAIL**" in report
    assert "阻断发布" in report
    assert "`C1`（必测）" in report

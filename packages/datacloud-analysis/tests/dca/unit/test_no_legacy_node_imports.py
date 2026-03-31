from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


LEGACY_NODE_NAMES = (
    "intent",
    "dag",
    "clarification",
    "loop",
    "agent_delegate",
    "direct_tool",
)


def test_tests_do_not_import_legacy_orchestration_nodes() -> None:
    tests_root = _repo_root() / "packages/datacloud-analysis/tests"
    violations: list[str] = []

    for path in tests_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for idx, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            for node_name in LEGACY_NODE_NAMES:
                token = f"from datacloud_analysis.orchestration.{node_name} import"
                if token in stripped:
                    violations.append(f"{path}:{idx}: {stripped}")
                    break

    assert not violations, "Found legacy node imports in tests:\n" + "\n".join(violations)

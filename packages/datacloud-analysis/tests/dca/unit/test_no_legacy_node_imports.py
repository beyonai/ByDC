"""Static checks: legacy orchestration nodes must not be reintroduced."""

from __future__ import annotations

import ast
from pathlib import Path

LEGACY_MODULES = {
    "datacloud_analysis.orchestration.intent",
    "datacloud_analysis.orchestration.dag",
    "datacloud_analysis.orchestration.clarification",
    "datacloud_analysis.orchestration.loop",
    "datacloud_analysis.orchestration.agent_delegate",
    "datacloud_analysis.orchestration.direct_tool",
}

LEGACY_NODE_NAMES = (
    "intent",
    "dag",
    "clarification",
    "loop",
    "agent_delegate",
    "direct_tool",
)

SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
TESTS_ROOT = Path(__file__).resolve().parents[2]


def _collect_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_src_has_no_legacy_orchestration_imports() -> None:
    violations: list[str] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        for imp in _collect_imports(py_file):
            if imp in LEGACY_MODULES:
                violations.append(f"{py_file.relative_to(SRC_ROOT)}: imports {imp}")
    assert not violations, "Legacy orchestration imports found:\n" + "\n".join(violations)


def test_tests_do_not_import_legacy_orchestration_nodes() -> None:
    violations: list[str] = []
    for path in TESTS_ROOT.rglob("*.py"):
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


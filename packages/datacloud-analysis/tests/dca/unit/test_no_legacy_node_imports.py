"""Static check: legacy orchestration nodes must not be reintroduced."""

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

SRC_ROOT = Path(__file__).resolve().parents[3] / "src"


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


def test_no_legacy_orchestration_imports() -> None:
    violations: list[str] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        for imp in _collect_imports(py_file):
            if imp in LEGACY_MODULES:
                violations.append(f"{py_file.relative_to(SRC_ROOT)}: imports {imp}")
    assert not violations, "Legacy orchestration imports found:\n" + "\n".join(violations)


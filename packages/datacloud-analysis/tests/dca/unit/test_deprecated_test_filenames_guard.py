"""Static guard: prevent reintroducing deprecated-style test filenames."""

from __future__ import annotations

from pathlib import Path

_ALLOWED_BASELINE = {
    # 历史保留：后续新增不得继续引入同类命名
    "unit\\test_no_legacy_node_imports.py",
    "unit\\test_prompts_v2.py",
}


def test_no_v2_v4_legacy_in_test_filenames() -> None:
    """Disallow newly introduced filenames containing v2/v4/legacy markers."""
    tests_root = Path(__file__).resolve().parents[1]
    flagged_files = sorted(
        str(path.relative_to(tests_root))
        for path in tests_root.rglob("test_*.py")
        if any(token in path.name.lower() for token in ("v2", "v4", "legacy"))
    )
    bad_files = [item for item in flagged_files if item not in _ALLOWED_BASELINE]
    assert not bad_files, (
        "新增测试文件名不应包含 v2/v4/legacy 标记，请重命名：\n" + "\n".join(bad_files)
    )

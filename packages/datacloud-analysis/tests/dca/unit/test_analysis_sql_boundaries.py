"""Architecture boundary checks for analysis layer."""

from __future__ import annotations

from pathlib import Path


def test_analysis_knowledge_module_does_not_reference_sqlalchemy_text_or_get_session() -> None:
    module_path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "datacloud_analysis"
        / "tools"
        / "knowledge.py"
    )
    source = module_path.read_text(encoding="utf-8")

    assert "sqlalchemy.text" not in source
    assert " get_session(" not in source
    assert (
        "from datacloud_knowledge.knowledge_search.db.connection import get_session" not in source
    )

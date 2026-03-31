from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def test_readme_documents_new_main_pipeline() -> None:
    repo_root = _repo_root()
    package_readme = (repo_root / "packages/datacloud-analysis/README.md").read_text(encoding="utf-8")
    backend_readme = (
        repo_root / "examples/e_commerce_demo/backend/README.md"
    ).read_text(encoding="utf-8")

    for content in (package_readme, backend_readme):
        assert "knowledge_enhance" in content
        assert "planning" in content
        assert "execution" in content
        assert "end" in content
        assert "intent ->" not in content
        assert "dag" not in content
        assert "loop" not in content

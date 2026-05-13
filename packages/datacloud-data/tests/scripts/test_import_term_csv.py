"""Tests for the import_term_csv script."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "import_term_csv.py"


def _write_csv(csv_path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "term_id",
        "term_code",
        "term_name",
        "desc_summary",
        "parent_term_id",
        "owl_doc_id",
        "domain_id",
        "term_type_code",
        "library_id",
        "term_tags",
        "ext_attrs",
        "created_time",
        "updated_time",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_import_term_csv_dry_run_succeeds(tmp_path: Path) -> None:
    csv_path = tmp_path / "term.csv"
    _write_csv(
        csv_path,
        [
            {
                "term_id": "LIB_001#GENERAL#TERM_001",
                "term_code": "TERM_001",
                "term_name": "测试术语",
                "desc_summary": "用于测试",
                "parent_term_id": "",
                "owl_doc_id": "",
                "domain_id": "DOMAIN_001",
                "term_type_code": "GENERAL",
                "library_id": "LIB_001",
                "term_tags": "",
                "ext_attrs": "",
                "created_time": "2026-04-16 15:22:38.810",
                "updated_time": "2026-04-16 15:22:38.810",
            }
        ],
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--csv-path", str(csv_path), "--dry-run"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Prepared 1 records" in result.stderr
    assert "Dry run succeeded" in result.stderr


def test_import_term_csv_rejects_duplicate_term_id(tmp_path: Path) -> None:
    csv_path = tmp_path / "term_duplicate.csv"
    duplicate_rows = [
        {
            "term_id": "LIB_001#GENERAL#TERM_001",
            "term_code": "TERM_001",
            "term_name": "测试术语1",
            "desc_summary": "",
            "parent_term_id": "",
            "owl_doc_id": "",
            "domain_id": "DOMAIN_001",
            "term_type_code": "GENERAL",
            "library_id": "LIB_001",
            "term_tags": "",
            "ext_attrs": "",
            "created_time": "2026-04-16 15:22:38.810",
            "updated_time": "2026-04-16 15:22:38.810",
        },
        {
            "term_id": "LIB_001#GENERAL#TERM_001",
            "term_code": "TERM_002",
            "term_name": "测试术语2",
            "desc_summary": "",
            "parent_term_id": "",
            "owl_doc_id": "",
            "domain_id": "DOMAIN_001",
            "term_type_code": "GENERAL",
            "library_id": "LIB_001",
            "term_tags": "",
            "ext_attrs": "",
            "created_time": "2026-04-16 15:22:38.810",
            "updated_time": "2026-04-16 15:22:38.810",
        },
    ]
    _write_csv(csv_path, duplicate_rows)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--csv-path", str(csv_path), "--dry-run"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "CSV 存在重复 term_id" in result.stderr


def test_import_term_csv_accepts_explicit_env_file_for_dry_run(tmp_path: Path) -> None:
    csv_path = tmp_path / "term.csv"
    env_path = tmp_path / "custom.env"
    _write_csv(
        csv_path,
        [
            {
                "term_id": "LIB_001#GENERAL#TERM_001",
                "term_code": "TERM_001",
                "term_name": "测试术语",
                "desc_summary": "用于测试",
                "parent_term_id": "",
                "owl_doc_id": "",
                "domain_id": "DOMAIN_001",
                "term_type_code": "GENERAL",
                "library_id": "LIB_001",
                "term_tags": "",
                "ext_attrs": "",
                "created_time": "2026-04-16 15:22:38.810",
                "updated_time": "2026-04-16 15:22:38.810",
            }
        ],
    )
    env_path.write_text("DATACLOUD_DB_HOST=127.0.0.1\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--csv-path",
            str(csv_path),
            "--env-file",
            str(env_path),
            "--dry-run",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Prepared 1 records" in result.stderr
    assert f"Loaded database env from {env_path}" in result.stderr

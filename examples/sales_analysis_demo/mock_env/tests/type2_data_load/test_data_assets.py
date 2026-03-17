"""Type2: tests for structured resource data readiness."""

from __future__ import annotations

import pytest


@pytest.mark.type2_data
def test_resource_data_directories_exist(resource_data_dir) -> None:
    assert resource_data_dir.exists()
    assert (resource_data_dir / "common").exists()
    assert (resource_data_dir / "modules").exists()


@pytest.mark.type2_data
def test_common_csv_files_exist(resource_data_dir) -> None:
    common_dir = resource_data_dir / "common"
    assert (common_dir / "po_users.csv").exists()
    assert (common_dir / "po_users_organization.csv").exists()
    assert (common_dir / "po_organization.csv").exists()


@pytest.mark.type2_data
def test_module_csv_count(resource_data_dir) -> None:
    csv_files = list((resource_data_dir / "modules").rglob("*.csv"))
    assert len(csv_files) >= 8

"""测试 fixtures — FakeRegistry + FakeRepository 注入。"""

from __future__ import annotations

import pytest

from tests.fake_registry import FakeRegistry, OntologyBaseEntry
from tests.fake_repository import FakeOntologyRepository


@pytest.fixture
def fake_registry() -> FakeRegistry:
    return FakeRegistry()


@pytest.fixture
def fake_repo() -> FakeOntologyRepository:
    return FakeOntologyRepository()


@pytest.fixture
def local_entry() -> OntologyBaseEntry:
    return OntologyBaseEntry(
        base_id="local_base",
        display_name="Local Base",
        owner_type="personal",
        source_type="LOCAL",
    )


@pytest.fixture
def remote_entry() -> OntologyBaseEntry:
    return OntologyBaseEntry(
        base_id="remote_base",
        display_name="Remote Base",
        owner_type="enterprise",
        source_type="REMOTE",
        source_url="https://example.com/api",
    )

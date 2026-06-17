"""OntologyService service layer unit tests.

Uses FakeRegistry + FakeRepository injection. Isolated - tests orchestration
logic and permission control only.
"""

from __future__ import annotations

import pytest
from datacloud_server.registry.registry import OntologyBaseEntry
from datacloud_server.services.ontology_service import OntologyService

from tests.fake_registry import FakeRegistry
from tests.fake_repository import FakeOntologyRepository


class FakeRemoteOntologyRepository(FakeOntologyRepository):
    """Fake repository that rejects all write operations (simulating REMOTE)."""

    _ERR_MSG = "Remote ontology base is read-only"

    def create_object(self, *args, **kwargs) -> dict:
        raise PermissionError(self._ERR_MSG)

    def delete_object(self, *args, **kwargs) -> None:
        raise PermissionError(self._ERR_MSG)

    def update_object(self, *args, **kwargs) -> dict:
        raise PermissionError(self._ERR_MSG)

    def create_view(self, *args, **kwargs) -> dict:
        raise PermissionError(self._ERR_MSG)

    def update_view(self, *args, **kwargs) -> dict:
        raise PermissionError(self._ERR_MSG)

    def delete_view(self, *args, **kwargs) -> None:
        raise PermissionError(self._ERR_MSG)

    def create_relation(self, *args, **kwargs) -> dict:
        raise PermissionError(self._ERR_MSG)

    def update_relation(self, *args, **kwargs) -> dict:
        raise PermissionError(self._ERR_MSG)

    def delete_relation(self, *args, **kwargs) -> None:
        raise PermissionError(self._ERR_MSG)

    def create_datasource(self, *args, **kwargs) -> dict:
        raise PermissionError(self._ERR_MSG)

    def delete_datasource(self, *args, **kwargs) -> None:
        raise PermissionError(self._ERR_MSG)

    def create_action(self, *args, **kwargs) -> dict:
        raise PermissionError(self._ERR_MSG)

    def update_action(self, *args, **kwargs) -> dict:
        raise PermissionError(self._ERR_MSG)

    def delete_action(self, *args, **kwargs) -> None:
        raise PermissionError(self._ERR_MSG)

    def import_owl(self, *args, **kwargs) -> dict:
        raise PermissionError(self._ERR_MSG)


@pytest.fixture
def local_repo() -> FakeOntologyRepository:
    return FakeOntologyRepository()


@pytest.fixture
def remote_repo() -> FakeRemoteOntologyRepository:
    return FakeRemoteOntologyRepository()


@pytest.fixture
def local_registry() -> FakeRegistry:
    reg = FakeRegistry()
    reg.register(
        OntologyBaseEntry(
            base_id="local_base",
            display_name="Local Base",
            description="",
            owner_type="personal",
            source_type="LOCAL",
        )
    )
    return reg


@pytest.fixture
def remote_registry() -> FakeRegistry:
    reg = FakeRegistry()
    reg.register(
        OntologyBaseEntry(
            base_id="remote_base",
            display_name="Remote Base",
            description="",
            owner_type="enterprise",
            source_type="REMOTE",
            source_url="https://example.com/api",
        )
    )
    return reg


@pytest.fixture
def svc(local_registry: FakeRegistry, local_repo: FakeOntologyRepository) -> OntologyService:
    return OntologyService(local_registry, {"LOCAL": local_repo})


@pytest.fixture
def svc_remote(
    remote_registry: FakeRegistry, local_repo: FakeOntologyRepository,
    remote_repo: FakeRemoteOntologyRepository,
) -> OntologyService:
    return OntologyService(
        remote_registry,
        {"LOCAL": local_repo, "REMOTE": remote_repo},
    )


class TestCreateOntologyBase:
    """Create OntologyBase - sourceType auto-derivation."""

    def test_create_local_base_derives_source_type(self, svc: OntologyService) -> None:
        result = svc.create_base(
            OntologyBaseEntry(base_id="my_base", display_name="My Base", owner_type="personal", description="", source_type="LOCAL"),
        )
        assert result["sourceType"] == "LOCAL"

    def test_create_remote_base_derives_source_type(self, svc: OntologyService) -> None:
        result = svc.create_base(
            OntologyBaseEntry(
                base_id="r_base",
                display_name="Remote Base",
                owner_type="enterprise",
                description="",
                source_type="REMOTE",
                source_url="https://external.example.com/api",
            ),
        )
        assert result["sourceType"] == "REMOTE"
        assert result["sourceUrl"] == "https://external.example.com/api"

    def test_duplicate_base_id_raises_error(self, svc: OntologyService) -> None:
        svc.create_base(OntologyBaseEntry(base_id="dup", display_name="First", description="", owner_type="personal", source_type="LOCAL"))
        with pytest.raises(ValueError, match="already exists"):
            svc.create_base(OntologyBaseEntry(base_id="dup", display_name="Second", description="", owner_type="personal", source_type="LOCAL"))

    def test_list_bases_returns_all(self, local_repo: FakeOntologyRepository) -> None:
        reg = FakeRegistry()
        svc_clean = OntologyService(reg, {"LOCAL": local_repo})
        svc_clean.create_base(OntologyBaseEntry(base_id="b1", display_name="B1", description="", owner_type="personal", source_type="LOCAL"))
        svc_clean.create_base(OntologyBaseEntry(base_id="b2", display_name="B2", description="", owner_type="personal", source_type="LOCAL"))
        result = svc_clean.list_bases()
        assert len(result) == 2
        assert {r["baseId"] for r in result} == {"b1", "b2"}


class TestObjectCRUD:
    """Object CRUD - REMOTE write denied, LOCAL works."""

    _OBJ_DATA: dict = {  # noqa: RUF012
        "objectCode": "customer",
        "objectName": "Customer",
        "fields": [{"fieldCode": "name", "fieldName": "Name", "fieldType": "STRING"}],
    }

    def test_create_object_on_remote_raises_403(self, svc_remote: OntologyService) -> None:
        with pytest.raises(PermissionError, match="read-only"):
            svc_remote.create_object("remote_base", "default", self._OBJ_DATA)

    def test_create_object_on_local_succeeds(self, svc: OntologyService) -> None:
        obj = svc.create_object("local_base", "default", self._OBJ_DATA)
        assert obj["objectCode"] == "customer"
        assert obj["objectName"] == "Customer"

    def test_create_duplicate_object_raises_error(self, svc: OntologyService) -> None:
        svc.create_object("local_base", "default", self._OBJ_DATA)
        with pytest.raises(ValueError, match="already exists"):
            svc.create_object("local_base", "default", self._OBJ_DATA)

    def test_delete_object_succeeds(self, svc: OntologyService) -> None:
        svc.create_object("local_base", "default", self._OBJ_DATA)
        svc.delete_object("local_base", "default", "customer")
        result = svc.get_object_detail("local_base", "default", "customer")
        assert result is None

    def test_delete_object_on_remote_raises_403(self, svc_remote: OntologyService) -> None:
        with pytest.raises(PermissionError, match="read-only"):
            svc_remote.delete_object("remote_base", "default", "nonexistent")


class TestSceneQuery:
    """Scene query operations."""

    def test_list_scenes_returns_from_adapter(self, svc: OntologyService) -> None:
        scenes = svc.list_scenes("local_base")
        assert isinstance(scenes, list)

    def test_list_scenes_nonexistent_base_raises_error(self, svc: OntologyService) -> None:
        with pytest.raises(KeyError, match="not found"):
            svc.list_scenes("nonexistent_base")

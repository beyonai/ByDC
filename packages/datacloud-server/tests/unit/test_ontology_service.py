"""OntologyService unit tests — now split across 3 domain Services.

Uses FakeRegistry + FakeRepository injection. Isolated - tests orchestration
logic and permission control only.
"""

from __future__ import annotations

import pytest
from datacloud_server.registry.registry import OntologyBaseEntry
from datacloud_server.services.adapter_router import AdapterRouter
from datacloud_server.services.ontology_base_service import OntologyBaseService
from datacloud_server.services.ontology_resource_service import OntologyResourceService

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
def base_svc(local_registry: FakeRegistry, local_repo: FakeOntologyRepository) -> OntologyBaseService:
    return OntologyBaseService(AdapterRouter(local_registry, {"LOCAL": local_repo}))


@pytest.fixture
def resource_svc(local_registry: FakeRegistry, local_repo: FakeOntologyRepository) -> OntologyResourceService:
    return OntologyResourceService(AdapterRouter(local_registry, {"LOCAL": local_repo}))


@pytest.fixture
def resource_svc_remote(
    remote_registry: FakeRegistry, local_repo: FakeOntologyRepository,
    remote_repo: FakeRemoteOntologyRepository,
) -> OntologyResourceService:
    return OntologyResourceService(
        AdapterRouter(remote_registry, {"LOCAL": local_repo, "REMOTE": remote_repo}),
    )


class TestCreateOntologyBase:
    """Create OntologyBase - sourceType auto-derivation."""

    def test_create_local_base_derives_source_type(self, base_svc: OntologyBaseService) -> None:
        result = base_svc.create_base(
            OntologyBaseEntry(base_id="my_base", display_name="My Base", owner_type="personal", description="", source_type="LOCAL"),
        )
        assert result["sourceType"] == "LOCAL"

    def test_create_remote_base_derives_source_type(self, base_svc: OntologyBaseService) -> None:
        result = base_svc.create_base(
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

    def test_duplicate_base_id_raises_error(self, base_svc: OntologyBaseService) -> None:
        base_svc.create_base(OntologyBaseEntry(base_id="dup", display_name="First", description="", owner_type="personal", source_type="LOCAL"))
        with pytest.raises(ValueError, match="already exists"):
            base_svc.create_base(OntologyBaseEntry(base_id="dup", display_name="Second", description="", owner_type="personal", source_type="LOCAL"))

    def test_list_bases_returns_all(self, local_repo: FakeOntologyRepository) -> None:
        reg = FakeRegistry()
        svc = OntologyBaseService(AdapterRouter(reg, {"LOCAL": local_repo}))
        svc.create_base(OntologyBaseEntry(base_id="b1", display_name="B1", description="", owner_type="personal", source_type="LOCAL"))
        svc.create_base(OntologyBaseEntry(base_id="b2", display_name="B2", description="", owner_type="personal", source_type="LOCAL"))
        result = svc.list_bases()
        assert len(result) == 2
        assert {r["baseId"] for r in result} == {"b1", "b2"}


class TestObjectCRUD:
    """Object CRUD - REMOTE write denied, LOCAL works."""

    _OBJ_DATA: dict = {  # noqa: RUF012
        "objectCode": "customer",
        "objectName": "Customer",
        "fields": [{"fieldCode": "name", "fieldName": "Name", "fieldType": "STRING"}],
    }

    def test_create_object_on_remote_raises_403(self, resource_svc_remote: OntologyResourceService) -> None:
        with pytest.raises(PermissionError, match="read-only"):
            resource_svc_remote.create_object("remote_base", "default", self._OBJ_DATA)

    def test_create_object_on_local_succeeds(self, resource_svc: OntologyResourceService) -> None:
        obj = resource_svc.create_object("local_base", "default", self._OBJ_DATA)
        assert obj["objectCode"] == "customer"
        assert obj["objectName"] == "Customer"

    def test_create_duplicate_object_raises_error(self, resource_svc: OntologyResourceService) -> None:
        resource_svc.create_object("local_base", "default", self._OBJ_DATA)
        with pytest.raises(ValueError, match="already exists"):
            resource_svc.create_object("local_base", "default", self._OBJ_DATA)

    def test_delete_object_succeeds(self, resource_svc: OntologyResourceService) -> None:
        resource_svc.create_object("local_base", "default", self._OBJ_DATA)
        resource_svc.delete_object("local_base", "default", "customer")
        result = resource_svc.get_object_detail("local_base", "default", "customer")
        assert result is None

    def test_delete_object_on_remote_raises_403(self, resource_svc_remote: OntologyResourceService) -> None:
        with pytest.raises(PermissionError, match="read-only"):
            resource_svc_remote.delete_object("remote_base", "default", "nonexistent")


class TestSceneQuery:
    """Scene query operations."""

    def test_list_scenes_returns_from_adapter(self, base_svc: OntologyBaseService) -> None:
        scenes = base_svc.list_scenes("local_base")
        assert isinstance(scenes, list)

    def test_list_scenes_nonexistent_base_raises_error(self, base_svc: OntologyBaseService) -> None:
        with pytest.raises(KeyError, match="not found"):
            base_svc.list_scenes("nonexistent_base")

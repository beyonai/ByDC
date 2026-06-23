"""Tests for DatacloudPlatform operations — CRUD, search, storage, import_owl."""

from __future__ import annotations

import io
import zipfile

import pytest

from datacloud_platform import DatacloudPlatform, OntologyBaseEntry
from datacloud_platform.models.shared import (
    MatchCandidate,
    MatchResult,
    ObjectSummary,
    ParsedOwlContent,
)

LOCAL = "local-base"
REMOTE = "remote-base"


class TestBaseCRUD:
    """Tests for list_bases / create_base / delete_base."""

    def test_list_bases(self, platform: DatacloudPlatform) -> None:
        """list_bases returns all registered bases as dicts."""
        bases = platform.list_bases()
        assert len(bases) == 2
        base_ids = {b["base_id"] for b in bases}
        assert base_ids >= {"local-base", "remote-base"}

    def test_create_base(self, platform: DatacloudPlatform) -> None:
        """create_base registers a new entry and returns it as dict."""
        entry = OntologyBaseEntry(
            base_id="new-base",
            display_name="新库",
            source_type="LOCAL",
        )
        result = platform.create_base(entry)
        assert result["base_id"] == "new-base"
        assert result["display_name"] == "新库"
        assert len(platform.list_bases()) == 3

    def test_create_duplicate_base_raises(self, platform: DatacloudPlatform) -> None:
        """Creating a base with an existing base_id raises ValueError."""
        entry = OntologyBaseEntry(
            base_id="local-base",
            display_name="Dup",
            source_type="LOCAL",
        )
        with pytest.raises(ValueError, match="already registered"):
            platform.create_base(entry)

    def test_delete_base(self, platform: DatacloudPlatform) -> None:
        """delete_base removes an existing base."""
        # First create a base we can delete
        entry = OntologyBaseEntry(
            base_id="to-delete",
            display_name="待删除",
            source_type="LOCAL",
        )
        platform.create_base(entry)
        assert len(platform.list_bases()) == 3

        platform.delete_base("to-delete")
        assert len(platform.list_bases()) == 2

        with pytest.raises(KeyError, match="not found"):
            platform.delete_base("to-delete")


class TestOntologyPassthrough:
    """Tests for ontology operations — load_ontology, get_objects, get_object_detail."""

    def test_load_ontology(self, platform: DatacloudPlatform) -> None:
        """load_ontology returns an OntologyQueryable handle."""
        loader = platform.load_ontology(LOCAL, "/fake/path")
        assert loader is not None
        # Verify it wraps the backend's _objects
        onto_local, *_ = platform._fakes  # type: ignore[attr-defined]
        onto_local._objects["obj1"] = ObjectSummary(  # type: ignore[index]
            object_code="obj1", object_name="对象1"
        )
        loader2 = platform.load_ontology(LOCAL, "/fake/path")
        assert "obj1" in loader2._classes  # type: ignore[attr-defined]

    def test_get_objects(self, platform: DatacloudPlatform) -> None:
        """get_objects returns all ObjectSummary from the ontology backend."""
        onto_local, *_ = platform._fakes  # type: ignore[attr-defined]
        onto_local._objects["obj_a"] = ObjectSummary(  # type: ignore[index]
            object_code="obj_a", object_name="A"
        )
        onto_local._objects["obj_b"] = ObjectSummary(  # type: ignore[index]
            object_code="obj_b", object_name="B"
        )
        objs = platform.get_objects(LOCAL)
        assert len(objs) == 2
        codes = {o.object_code for o in objs}
        assert codes == {"obj_a", "obj_b"}

    def test_get_object_detail(self, platform: DatacloudPlatform) -> None:
        """get_object_detail looks up a single object by code."""
        onto_local, *_ = platform._fakes  # type: ignore[attr-defined]
        onto_local._objects["obj_x"] = ObjectSummary(  # type: ignore[index]
            object_code="obj_x", object_name="X"
        )
        detail = platform.get_object_detail(LOCAL, "obj_x")
        assert detail is not None
        assert detail.object_code == "obj_x"

        missing = platform.get_object_detail(LOCAL, "no_such")
        assert missing is None


class TestSearch:
    """Tests for search — search_candidates + disambiguate flow."""

    def test_search_flow(self, platform: DatacloudPlatform) -> None:
        """search() calls search_candidates then disambiguate."""
        _, _, know, *_ = platform._fakes  # type: ignore[attr-defined]

        c1 = MatchCandidate(
            term_id="t1",
            term_name="收入",
            term_type_code="metric",
            match_type="semantic",
            confidence=0.9,
            score=0.9,
        )
        c2 = MatchCandidate(
            term_id="t2",
            term_name="成本",
            term_type_code="metric",
            match_type="semantic",
            confidence=0.8,
            score=0.8,
        )
        know.candidates = [c1, c2]

        result = MatchResult(
            exact={"收入": (c1,), "成本": (c2,)},
            fuzzy={},
        )
        know._disambiguated = [result]

        results = platform.search(LOCAL, "财务指标")
        assert len(results) == 1
        assert results[0].exact == {"收入": (c1,), "成本": (c2,)}


class TestStoragePassthrough:
    """Tests for store_result / get_result / delete_result."""

    def test_store_and_get_result(self, platform: DatacloudPlatform) -> None:
        """store_result persists data and returns file_id; get_result retrieves it."""
        fid = platform.store_result(LOCAL, "report", b"content")
        assert isinstance(fid, str)
        assert len(fid) > 0
        assert platform.get_result(LOCAL, fid) == b"content"

    def test_store_with_metadata(self, platform: DatacloudPlatform) -> None:
        """store_result accepts optional metadata."""
        fid = platform.store_result(LOCAL, "key1", b"data", metadata={"author": "test"})
        _, _, _, _, stor = platform._fakes  # type: ignore[attr-defined]
        assert stor._meta.get(fid) == {"author": "test"}  # type: ignore[attr-defined]

    def test_delete_result(self, platform: DatacloudPlatform) -> None:
        """delete_result removes a stored file."""
        fid = platform.store_result(LOCAL, "temp", b"xyz")
        platform.delete_result(LOCAL, fid)
        with pytest.raises(KeyError):
            platform.get_result(LOCAL, fid)

    def test_remote_storage_permission_error(self, platform: DatacloudPlatform) -> None:
        """REMOTE base store_result raises PermissionError (storage=none)."""
        with pytest.raises(PermissionError, match="Storage not available"):
            platform.store_result(REMOTE, "k", b"v")


class TestImportOwl:
    """Tests for import_owl orchestration."""

    def test_import_owl_orchestration(self, platform: DatacloudPlatform) -> None:
        """import_owl unzips → parse → create objects/views/relations → sync terms."""
        onto_local, _, know, *_ = platform._fakes  # type: ignore[attr-defined]

        # Preset parsed OWL content
        onto_local._parsed = ParsedOwlContent(
            objects=[
                {
                    "object_code": "obj_owl",
                    "object_name": "OWL对象",
                    "object_source": "owl_import",
                    "properties": [{"field_code": "f1", "field_name": "字段1"}],
                }
            ],
            views=[{"view_code": "v1", "view_name": "视图1"}],
            relations=[{"relation_code": "r1", "source": "A", "target": "B"}],
        )

        # Create a minimal zip file
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("ontology.owl", "<rdf:RDF/>")
        zip_bytes = buf.getvalue()

        summary = platform.import_owl(LOCAL, "scene1", zip_bytes)
        assert isinstance(summary, dict)
        assert "objects" in summary
        assert summary["objects"] >= 0

        # Verify object was created
        assert len(onto_local._created_objects) >= 1  # type: ignore[attr-defined]

        # Verify terms were synced
        assert "obj_owl" in know._synced  # type: ignore[attr-defined]


class TestRemoteWriteDenied:
    """Tests verifying REMOTE write operations are denied by the backend itself."""

    def test_remote_update_object_permission_error(
        self, platform: DatacloudPlatform
    ) -> None:
        """REMOTE update_object raises PermissionError from the readonly backend."""
        with pytest.raises(PermissionError, match="read-only"):
            platform.update_object(REMOTE, "obj1", {})

    def test_remote_delete_object_permission_error(
        self, platform: DatacloudPlatform
    ) -> None:
        """REMOTE delete_object raises PermissionError from the readonly backend."""
        with pytest.raises(PermissionError, match="read-only"):
            platform.delete_object(REMOTE, "obj1")

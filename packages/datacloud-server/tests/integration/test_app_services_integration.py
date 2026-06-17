"""Integration tests for search_instances, graph_query and graph_path.

Uses OWL data loaded via the shared owl_data_dir fixture (see conftest or
test_local_adapter_integration.py).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from datacloud_server.adapters.local_adapter import LocalOntologyAdapter
from datacloud_server.storage.json_writer import JSONWriter


@pytest.fixture
def owl_data_dir(tmp_path: Path) -> Path:
    """Copy owl_example into tmp_path as a base directory."""
    src = Path("/workspace/projects/ontology_server/owl_example")
    dst = tmp_path / "owl_example"
    shutil.copytree(src, dst)
    return tmp_path


@pytest.fixture
def adapter(owl_data_dir: Path) -> LocalOntologyAdapter:
    """Create LocalOntologyAdapter with OWL data loaded."""
    writer = JSONWriter()
    return LocalOntologyAdapter(str(owl_data_dir), writer)


# ── search_instances ──────────────────────────────────────────────


class TestSearchInstances:
    """Keyword-based instance search over loaded ontology objects."""

    def test_search_by_keyword_finds_customer(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.search_instances(
            "owl_example", object_code="", where={"keyword": "customer"},
        )
        data = result["data"]
        assert len(data) > 0
        codes = {item["objectCode"] for item in data}
        assert "by_customer" in codes

    def test_search_by_object_name_finds_chinese(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.search_instances(
            "owl_example", object_code="", where={"keyword": "客户"},
        )
        data = result["data"]
        assert len(data) > 0
        codes = {item["objectCode"] for item in data}
        assert "by_customer" in codes

    def test_search_by_field_keyword(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.search_instances(
            "owl_example", object_code="", where={"keyword": "customer_code"},
        )
        data = result["data"]
        assert len(data) > 0
        assert result["totalCount"] == len(data)

    def test_search_with_object_code_filter(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.search_instances(
            "owl_example",
            object_code="by_opportunity",
            where={"keyword": "客户"},
        )
        data = result["data"]
        codes = {item["objectCode"] for item in data}
        assert codes == {"by_opportunity"}

    def test_search_by_english_code_filter(self, adapter: LocalOntologyAdapter) -> None:
        """Search with keyword that appears in the specific object's field names."""
        result = adapter.search_instances(
            "owl_example",
            object_code="by_opportunity",
            where={"keyword": "opp"},
        )
        data = result["data"]
        assert len(data) > 0
        codes = {item["objectCode"] for item in data}
        assert codes == {"by_opportunity"}

    def test_search_no_keyword_returns_all(self, adapter: LocalOntologyAdapter) -> None:
        """Empty keyword means 'match all' — returns all objects."""
        result = adapter.search_instances("owl_example", object_code="")
        # Returns all 8 objects
        assert result["totalCount"] == 8
        assert len(result["data"]) == 8

    def test_search_nonexistent_keyword_returns_empty(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.search_instances(
            "owl_example", object_code="", where={"keyword": "xyznonexistent99"},
        )
        assert result["data"] == []
        assert result["totalCount"] == 0

    def test_search_result_structure(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.search_instances(
            "owl_example", object_code="", where={"keyword": "customer"},
        )
        for item in result["data"]:
            assert "objectCode" in item
            assert "objectName" in item
            assert "objectDesc" in item


# ── graph_query ────────────────────────────────────────────────────


class TestGraphQuery:
    """Graph query based on object relations."""

    def test_graph_query_returns_nodes_and_edges(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.graph_query("owl_example", "object", object_code=[])
        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) > 0

    def test_graph_query_filter_by_object_codes(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.graph_query(
            "owl_example",
            "object",
            object_code=["by_customer", "by_opportunity", "by_project"],
        )
        node_codes = {n["code"] for n in result["nodes"]}
        assert node_codes == {"by_customer", "by_opportunity", "by_project"}
        # edges only between filtered objects
        for edge in result["edges"]:
            assert edge["source"] in node_codes
            assert edge["target"] in node_codes

    def test_graph_query_with_depth(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.graph_query(
            "owl_example",
            "object",
            object_code=["by_customer"],
            step=2,
        )
        node_codes = {n["code"] for n in result["nodes"]}
        # by_customer + directly connected: by_opportunity, by_project, po_users, po_organization
        assert "by_customer" in node_codes
        assert "by_opportunity" in node_codes
        assert "by_project" in node_codes

    def test_graph_query_empty_object_codes(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.graph_query(
            "owl_example", "object", object_code=["nonexistent"],
        )
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_graph_query_node_has_label(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.graph_query("owl_example", "object", object_code=[])
        for node in result["nodes"]:
            assert "code" in node
            assert "label" in node


# ── graph_path ──────────────────────────────────────────────────────


class TestGraphPath:
    """Shortest path between two objects in the relation graph."""

    def test_graph_path_direct_neighbors(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.graph_path(
            "owl_example",
            "object",
            start_node="by_customer",
            end_node="by_opportunity",
        )
        assert result["path"] == ["by_customer", "by_opportunity"]
        assert result["hops"] == 1
        assert len(result["edges"]) == 1

    def test_graph_path_two_hops(self, adapter: LocalOntologyAdapter) -> None:
        # by_customer -> by_project -> by_project_task
        result = adapter.graph_path(
            "owl_example",
            "object",
            start_node="by_customer",
            end_node="by_project_task",
        )
        assert result["hops"] == 2
        assert result["path"][0] == "by_customer"
        assert result["path"][-1] == "by_project_task"

    def test_graph_path_no_path(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.graph_path(
            "owl_example",
            "object",
            start_node="by_customer",
            end_node="nonexistent",
        )
        assert result["path"] == []
        assert result["hops"] == -1
        assert result["edges"] == []

    def test_graph_path_same_node(self, adapter: LocalOntologyAdapter) -> None:
        result = adapter.graph_path(
            "owl_example",
            "object",
            start_node="by_customer",
            end_node="by_customer",
        )
        assert result["path"] == ["by_customer"]
        assert result["hops"] == 0
        assert result["edges"] == []

    def test_graph_path_three_hops(self, adapter: LocalOntologyAdapter) -> None:
        # by_customer -> by_project -> by_rd_task (2 hops)
        result = adapter.graph_path(
            "owl_example",
            "object",
            start_node="by_customer",
            end_node="by_rd_task",
        )
        assert result["hops"] == 2
        assert result["path"][0] == "by_customer"
        assert result["path"][-1] == "by_rd_task"

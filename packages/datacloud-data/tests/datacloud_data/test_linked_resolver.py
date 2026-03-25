"""LinkedResolver 测试：API + DB 跨源 linked 批量解析。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from datacloud_data_sdk.executor.linked_resolver import (
    resolve_api_linked_batch,
    resolve_db_linked_batch,
)
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.models import OntologyField, OntologyRelation


def _load_scenario_api_linked() -> OntologyLoader:
    path = Path(__file__).resolve().parent.parent / "fixtures" / "ontology" / "scenario_api_linked.json"
    loader = OntologyLoader()
    loader.load_from_path(path)
    return loader


def _load_scenario_db_linked() -> OntologyLoader:
    path = Path(__file__).resolve().parent.parent / "fixtures" / "ontology" / "scenario_db_linked.json"
    loader = OntologyLoader()
    loader.load_from_path(path)
    return loader


def _get_api_relation(loader: OntologyLoader) -> OntologyRelation:
    for r in loader.get_ontology_relations():
        if r.relation_code == "customer_has_opportunities" and r.resolve_action_code:
            return r
    raise ValueError("relation not found")


def _get_api_field(loader: OntologyLoader) -> OntologyField:
    cls = loader.get_ontology_class("customer")
    for f in cls.fields:
        if f.field_code == "opportunities":
            return f
    raise ValueError("field not found")


def _get_db_relation(loader: OntologyLoader) -> OntologyRelation:
    for r in loader.get_ontology_relations():
        if r.relation_code == "customer_has_opportunities":
            return r
    raise ValueError("relation not found")


def _get_db_field(loader: OntologyLoader) -> OntologyField:
    cls = loader.get_ontology_class("customer")
    for f in cls.fields:
        if f.field_code == "opportunities":
            return f
    raise ValueError("field not found")


@pytest.mark.asyncio
async def test_resolve_api_linked_single() -> None:
    """API linked 单条：mock invoke_action 返回统一格式 {records: [{id: 1}]}。"""
    loader = _load_scenario_api_linked()
    relation = _get_api_relation(loader)
    field = _get_api_field(loader)
    parents = [{"customer_id": "c1"}]

    mock_obj = AsyncMock()
    mock_obj.invoke_action = AsyncMock(return_value={"records": [{"id": 1}], "total": 1, "meta": {}})

    with patch.object(loader, "get_object", return_value=mock_obj):
        result = await resolve_api_linked_batch(loader, parents, field, relation)

    assert result == [[{"id": 1}]]
    mock_obj.invoke_action.assert_called_once_with("query_opportunities_by_customer", {"customerId": "c1"})


@pytest.mark.asyncio
async def test_resolve_db_linked_batch() -> None:
    """DB linked 批量：scenario_db_linked 数据，parents 两个 customer，断言返回对应 opportunities。"""
    from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager

    loader = _load_scenario_db_linked()
    ds_manager = DataSourceManager(loader._config.datasource_configs)
    connector = ds_manager.get_connector("test_db")
    await connector.execute("CREATE TABLE IF NOT EXISTS customer (id INTEGER, name TEXT, customer_id TEXT)")
    await connector.execute("CREATE TABLE IF NOT EXISTS opportunity (id INTEGER, amount REAL, customer_id TEXT)")
    await connector.execute("DELETE FROM opportunity")
    await connector.execute("DELETE FROM customer")
    await connector.execute("INSERT INTO customer VALUES (1, 'c1', 'c1'), (2, 'c2', 'c2')")
    await connector.execute(
        "INSERT INTO opportunity VALUES (1, 100, 'c1'), (2, 200, 'c1'), (3, 150, 'c2')"
    )

    relation = _get_db_relation(loader)
    field = _get_db_field(loader)
    parents = [{"customer_id": "c1"}, {"customer_id": "c2"}]

    result = await resolve_db_linked_batch(loader, parents, field, relation, ds_manager)

    assert len(result) == 2
    assert len(result[0]) == 2  # c1 有 2 个 opportunity
    assert len(result[1]) == 1  # c2 有 1 个 opportunity
    ids_0 = {r["id"] for r in result[0]}
    ids_1 = {r["id"] for r in result[1]}
    assert ids_0 == {1, 2}
    assert ids_1 == {3}

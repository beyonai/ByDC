"""
OQL 路由层测试
"""

import pytest
from datacloud_data_sdk.oql.router import OqlRouter
from datacloud_data_sdk.oql import OQLError, OQLErrorCode
from tests.datacloud_data.fixtures.oql_test_data import (
    MockRegistry,
    MockTermResolver,
    MockDatasourceRegistry,
)


class MockExecutor:
    """Mock 执行器"""

    def __init__(self, return_value=None):
        self.return_value = return_value or []
        self.last_task = None

    def run(self, task):
        self.last_task = task
        return self.return_value


class TestOqlRouter:
    """测试 OQL 路由器"""

    def test_route_single_source_db(self):
        """路由单源 DB 查询"""
        registry = MockRegistry()
        term_resolver = MockTermResolver()
        executor = MockExecutor([{"flight_id": "F001", "status": "completed"}])
        datasource_registry = MockDatasourceRegistry()

        router = OqlRouter(registry)
        result = router.execute_single_step(
            {
                "object": "Flight",
                "fields": ["flight_id", "status"],
                "where": [{"field": "status", "op": "eq", "value": "completed"}],
            },
            term_resolver,
            executor,
            datasource_registry,
        )

        assert len(result) == 1
        assert result[0]["flight_id"] == "F001"

    def test_route_api_object(self):
        """路由 API 对象查询"""
        registry = MockRegistry()
        term_resolver = MockTermResolver()
        executor = MockExecutor([{"manual_id": "M001", "manual_name": "Manual A"}])
        datasource_registry = MockDatasourceRegistry()

        router = OqlRouter(registry)
        result = router.execute_single_step(
            {
                "object": "Manual",
                "fields": ["manual_id", "manual_name"],
            },
            term_resolver,
            executor,
            datasource_registry,
        )

        assert len(result) == 1
        assert result[0]["manual_id"] == "M001"

    def test_route_api_with_metrics_fails(self):
        """API 对象不支持 metrics"""
        registry = MockRegistry()
        term_resolver = MockTermResolver()
        executor = MockExecutor()
        datasource_registry = MockDatasourceRegistry()

        router = OqlRouter(registry)

        with pytest.raises(OQLError) as exc_info:
            router.execute_single_step(
                {
                    "object": "Manual",
                    "fields": ["manual_id"],
                    "metrics": [{"field": "manual_id", "aggregation": "count"}],
                },
                term_resolver,
                executor,
                datasource_registry,
            )
        assert exc_info.value.code == OQLErrorCode.OQL_ERR_UNSUPPORTED_OPERATION

    def test_route_api_with_include_links_fails(self):
        """API 对象不支持 include_links"""
        registry = MockRegistry()
        term_resolver = MockTermResolver()
        executor = MockExecutor()
        datasource_registry = MockDatasourceRegistry()

        router = OqlRouter(registry)

        with pytest.raises(OQLError) as exc_info:
            router.execute_single_step(
                {
                    "object": "Manual",
                    "fields": ["manual_id"],
                    "include_links": [{"path": "something"}],
                },
                term_resolver,
                executor,
                datasource_registry,
            )
        assert exc_info.value.code == OQLErrorCode.OQL_ERR_UNSUPPORTED_OPERATION

    def test_route_pipeline(self):
        """路由 Pipeline 查询"""
        registry = MockRegistry()
        term_resolver = MockTermResolver()
        executor = MockExecutor([{"flight_id": "F001"}])
        datasource_registry = MockDatasourceRegistry()

        router = OqlRouter(registry)
        result = router.route(
            [
                {
                    "step_id": "step1",
                    "parameters": {
                        "object": "Flight",
                        "fields": ["flight_id"],
                    },
                }
            ],
            term_resolver,
            executor,
            datasource_registry,
        )

        assert len(result) == 1
        assert result[0]["flight_id"] == "F001"

    def test_unknown_object(self):
        """未知对象"""
        registry = MockRegistry()
        term_resolver = MockTermResolver()
        executor = MockExecutor()
        datasource_registry = MockDatasourceRegistry()

        router = OqlRouter(registry)

        with pytest.raises(OQLError) as exc_info:
            router.execute_single_step(
                {
                    "object": "UnknownObject",
                    "fields": ["id"],
                },
                term_resolver,
                executor,
                datasource_registry,
            )
        assert exc_info.value.code == OQLErrorCode.OQL_ERR_UNKNOWN_OBJECT

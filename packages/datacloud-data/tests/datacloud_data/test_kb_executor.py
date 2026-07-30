from __future__ import annotations

import csv
from pathlib import Path

import pytest
from datacloud_data_sdk.exceptions import DataSourceUnavailableError, KbExecutionError
from datacloud_data_sdk.executor.kb_executor import KbExecutor
from datacloud_data_sdk.executor.kb_search_backend import (
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)
from datacloud_data_sdk.executor.models import KbExecTask
from datacloud_data_sdk.executor.step_results import StepResults


class CapturingSearchBackend:
    def __init__(self, records: list[dict] | None = None) -> None:
        self.request: KnowledgeSearchRequest | None = None
        self.records = records or []

    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        self.request = request
        return KnowledgeSearchResult(records=self.records, total=len(self.records))


def _read_csv_records(path: str) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


@pytest.mark.asyncio
async def test_kb_executor_uses_configured_resource_id_and_writes_csv(
    tmp_path: Path,
) -> None:
    backend = CapturingSearchBackend([{"content": "自定义内容", "source": "kb_docs"}])
    executor = KbExecutor(
        kb_configs={"kb_docs": {"kb_resource_id": "1234567890"}},
        csv_base_dir=str(tmp_path),
        search_backend=backend,
    )
    task = KbExecTask(
        datasource_alias="kb_docs",
        query="自定义检索",
        tags={"category": "manual"},
        output_ref="kb_out",
    )

    csv_path = await executor.execute(task, "req1", StepResults())

    assert backend.request == KnowledgeSearchRequest(
        object_code="kb_docs",
        datasource_alias="kb_docs",
        query="自定义检索",
        filters={"category": "manual"},
        limit=10,
        kb_resource_id="1234567890",
    )
    assert _read_csv_records(csv_path) == [{"content": "自定义内容", "source": "kb_docs"}]


@pytest.mark.asyncio
async def test_kb_executor_task_resource_id_overrides_config(tmp_path: Path) -> None:
    backend = CapturingSearchBackend()
    executor = KbExecutor(
        kb_configs={"kb_docs": {"kb_resource_id": "100"}},
        csv_base_dir=str(tmp_path),
        search_backend=backend,
    )

    await executor.execute(
        KbExecTask(
            datasource_alias="kb_docs",
            query="test",
            output_ref="out",
            kb_resource_id="200",
        ),
        "req1",
        StepResults(),
    )

    assert backend.request is not None
    assert backend.request.kb_resource_id == "200"


@pytest.mark.asyncio
async def test_kb_executor_raises_on_missing_datasource() -> None:
    executor = KbExecutor(
        kb_configs={"kb_docs": {"kb_resource_id": "1234567890"}},
        search_backend=CapturingSearchBackend(),
    )

    with pytest.raises(DataSourceUnavailableError):
        await executor.execute(
            KbExecTask(
                datasource_alias="unknown_kb",
                query="test",
                output_ref="out",
            ),
            "req1",
            StepResults(),
        )


@pytest.mark.asyncio
async def test_kb_executor_rejects_missing_resource_id() -> None:
    backend = CapturingSearchBackend()
    executor = KbExecutor(
        kb_configs={"kb_docs": {}},
        search_backend=backend,
    )

    with pytest.raises(KbExecutionError, match="kb_resource_id is required"):
        await executor.execute(
            KbExecTask(
                datasource_alias="kb_docs",
                query="test",
                output_ref="out",
            ),
            "req1",
            StepResults(),
        )

    assert backend.request is None

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from datacloud_service.worker import DataCloudWorker


@dataclass
class _FakeTaskPaths:
    skills_public: Path
    skills_private: Path


class _FakeSkillLoader:
    def __init__(self, _task_paths: Any) -> None:
        pass

    def load_all(self) -> dict[str, dict[str, Any]]:
        async def _async_skill(**params: Any) -> dict[str, Any]:
            return {"async": True, "params": params}

        def _sync_skill(**params: Any) -> dict[str, Any]:
            return {"sync": True, "params": params}

        return {
            "async_skill": {"run": _async_skill},
            "sync_skill": {"run": _sync_skill},
        }


@pytest.mark.asyncio
async def test_worker_load_skill_capabilities_wraps_sync_and_async(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_paths_mod = ModuleType("datacloud_analysis.workspace.paths")
    fake_loader_mod = ModuleType("datacloud_analysis.workspace.skills_loader")

    def _build_task_paths(*, user_id: str, task_id: str) -> _FakeTaskPaths:
        _ = user_id, task_id
        return _FakeTaskPaths(skills_public=tmp_path, skills_private=tmp_path)

    fake_paths_mod.build_task_paths = _build_task_paths
    fake_loader_mod.SkillLoader = _FakeSkillLoader

    monkeypatch.setitem(sys.modules, "datacloud_analysis.workspace.paths", fake_paths_mod)
    monkeypatch.setitem(sys.modules, "datacloud_analysis.workspace.skills_loader", fake_loader_mod)

    worker = DataCloudWorker(worker_id="worker-test")
    skills = worker._load_skill_capabilities(user_id="u1", task_id="t1")

    assert sorted(skills.keys()) == ["async_skill", "sync_skill"]
    async_out = await skills["async_skill"](x=1)
    sync_out = await skills["sync_skill"](y=2)
    assert async_out == {"async": True, "params": {"x": 1}}
    assert sync_out == {"sync": True, "params": {"y": 2}}

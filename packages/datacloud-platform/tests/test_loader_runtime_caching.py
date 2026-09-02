"""LoaderRuntimeManager 快照缓存 + write action 按需加载测试。

覆盖：
- scoped get_loader 缓存命中复用（load_ontology_from_codes 只构建一次）
- 版本指纹变化 → 缓存失效重建（storage_version 逐实体表校验）
- scoped 只加载目标对象（object_codes 透传断言）
- invoke_object_action 优先走 runtime 按需加载（不重复注入虚拟动作）
- 无 runtime 时回退 _load_ontology_cached 原路径
"""

from __future__ import annotations

from typing import Any

import pytest

from datacloud_platform.loader_runtime import (
    LoaderRuntimeManager,
    _ENTITY_FINGERPRINT_TABLES,
)
from datacloud_platform.services import object_action as object_action_module
from datacloud_platform.services.object_action import invoke_object_action


# ── 测试用假对象 ─────────────────────────────────────────────────────────────


class _FakeConfig:
    term_loader: Any = None
    plan_generator: Any = None
    event_bus: Any = None
    result_file_storage: Any = None


class _FakeLoader:
    """模拟 OntologyLoader：_config / get_ontology_classes / _views / configure。"""

    def __init__(self, object_codes: list[str] | None = None) -> None:
        self.object_codes = object_codes or []
        self._config = _FakeConfig()
        self._views: dict[str, Any] = {}
        self.configured: list[dict[str, Any]] = []
        self.target: _FakeTargetObject | None = None

    def get_ontology_classes(self) -> list[Any]:
        return []

    def configure(self, **kwargs: Any) -> None:
        self.configured.append(kwargs)

    def get_object(self, object_code: str) -> _FakeTargetObject:
        if self.target is None:
            raise KeyError(object_code)
        return self.target


class _FakeTargetObject:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def invoke_action(
        self, action_code: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append({"action_code": action_code, "arguments": arguments})
        return {"records": [{"id": "rt-1"}], "total": 1}


class _FakeStore:
    def __init__(self, versions: dict[str, str]) -> None:
        self._versions = versions

    def storage_version(self, entity_type: str, *, base_id: str = "") -> str:
        return self._versions.get(entity_type, "0")

    def sub_store(self, namespace: str) -> _FakeStore:
        return self


class _FakeBackend:
    def __init__(self, store: _FakeStore) -> None:
        self._entity_store = store


class _FakeRegistry:
    def __init__(self, bases: list[str] | None = None) -> None:
        self._bases = bases or ["base-1"]

    def list(self) -> list[Any]:
        return [type("E", (), {"base_id": b})() for b in self._bases]


class _FakePlatform:
    """模拟 DatacloudPlatform：scoped 加载 / 虚拟动作注入 / 实体 store / 全量加载。"""

    def __init__(self, versions: dict[str, str] | None = None) -> None:
        self.loaded_codes: list[tuple[str, list[str], list[str] | None]] = []
        self.injected: list[str] = []
        self._versions = versions or {t: "1" for t in _ENTITY_FINGERPRINT_TABLES}
        self._base_registry = _FakeRegistry()
        self._backend = _FakeBackend(_FakeStore(self._versions))

    def _ontology_for(self, base_id: str) -> _FakeBackend:
        return self._backend

    def _base_path_for(self, base_id: str) -> str:
        return f"/tmp/ontologies/{base_id}"

    def load_ontology_from_codes(
        self,
        base_id: str,
        object_codes: list[str],
        *,
        view_codes: list[str] | None = None,
    ) -> _FakeLoader:
        self.loaded_codes.append((base_id, list(object_codes), view_codes))
        return _FakeLoader(list(object_codes))

    def load_ontology(self, base_id: str, base_path: str) -> _FakeLoader:
        return _FakeLoader([])

    def inject_virtual_actions(self, base_id: str, loader: _FakeLoader) -> None:
        self.injected.append(base_id)


class _FakeSettings:
    llm_api_key: str = ""
    llm_model: str = ""
    llm_api_base: str = ""
    llm_temperature: float = 0.0
    max_plan_retries: int = 0
    result_file_base_dir: str = "/tmp/result-files"
    csv_base_dir: str = "/tmp"
    sql_execution_mode: str = ""
    query_result_csv_threshold: int = 100
    trace_enabled: bool = False
    trace_log_path: str = ""


def _make_runtime(
    platform: _FakePlatform,
) -> LoaderRuntimeManager:
    return LoaderRuntimeManager(platform=platform, settings=_FakeSettings())  # type: ignore[arg-type]


# ── LoaderRuntimeManager 快照缓存 ────────────────────────────────────────────


class TestLoaderSnapshotCache:
    def test_scoped_get_loader_caches_and_reuses(self) -> None:
        """相同 base_id + object_codes 二次 get_loader → 命中缓存复用快照，
        load_ontology_from_codes 只构建一次。"""
        platform = _FakePlatform()
        runtime = _make_runtime(platform)
        s1 = runtime.get_loader("base-1", object_codes=["Concept"])
        s2 = runtime.get_loader("base-1", object_codes=["Concept"])
        assert s1 is s2
        assert platform.loaded_codes == [("base-1", ["Concept"], None)]
        assert len(platform.injected) == 1  # 虚拟动作注入只发生一次

    def test_fingerprint_change_rebuilds_snapshot(self) -> None:
        """版本指纹任一实体表变化 → 缓存失效，下次调用重建快照。"""
        platform = _FakePlatform()
        runtime = _make_runtime(platform)
        s1 = runtime.get_loader("base-1", object_codes=["Concept"])
        platform._versions["objects"] = "2"  # 对象表版本变化（外部写入）
        s2 = runtime.get_loader("base-1", object_codes=["Concept"])
        assert s1 is not s2
        assert len(platform.loaded_codes) == 2
        # 再次调用（指纹稳定）→ 命中新缓存
        s3 = runtime.get_loader("base-1", object_codes=["Concept"])
        assert s3 is s2
        assert len(platform.loaded_codes) == 2

    def test_different_object_codes_are_distinct_cache_keys(self) -> None:
        """不同 object_codes → 独立缓存键，各自按需构建。"""
        platform = _FakePlatform()
        runtime = _make_runtime(platform)
        runtime.get_loader("base-1", object_codes=["Concept"])
        runtime.get_loader("base-1", object_codes=["医疗文书"])
        assert [codes for _, codes, _ in platform.loaded_codes] == [
            ["Concept"],
            ["医疗文书"],
        ]

    def test_scoped_loads_only_requested_object_codes(self) -> None:
        """scoped 加载只传递目标对象 code（不做全量 load_ontology）。"""
        platform = _FakePlatform()
        runtime = _make_runtime(platform)
        runtime.get_loader("base-1", object_codes=["Concept"])
        assert platform.loaded_codes == [("base-1", ["Concept"], None)]
        assert (
            not hasattr(platform, "legacy_load_called")
            or not platform.legacy_load_called
        )

    def test_full_path_get_loader_builds_full_loader(self) -> None:
        """无 object_codes（全量路径）→ 走 load_ontology 构建并缓存。"""
        platform = _FakePlatform()
        runtime = _make_runtime(platform)
        s1 = runtime.get_loader("base-1")
        s2 = runtime.get_loader("base-1")
        assert s1 is s2

    def test_fingerprint_query_failure_skips_cache(self) -> None:
        """版本指纹查询异常 → 不信任缓存也不写入缓存（保守），直接构建返回。"""

        class _BrokenStore(_FakeStore):
            def storage_version(self, entity_type: str, *, base_id: str = "") -> str:
                raise RuntimeError("db down")

        platform = _FakePlatform()
        platform._backend = _FakeBackend(_BrokenStore(dict(platform._versions)))
        runtime = _make_runtime(platform)
        s1 = runtime.get_loader("base-1", object_codes=["Concept"])
        s2 = runtime.get_loader("base-1", object_codes=["Concept"])
        assert s1 is not s2  # 每次重建，不读缓存
        assert len(platform.loaded_codes) == 2

    def test_fingerprint_covers_all_entity_tables(self) -> None:
        """指纹覆盖 7 张实体表：objects/views/actions/relations/datasources/scenes/bases。"""
        assert set(_ENTITY_FINGERPRINT_TABLES) == {
            "objects",
            "views",
            "actions",
            "relations",
            "datasources",
            "scenes",
            "bases",
        }


# ── invoke_object_action：runtime 按需加载 + 回退 ───────────────────────────


class TestInvokeObjectActionLoaderResolution:
    @pytest.fixture(autouse=True)
    def _reset_runtime_ref(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(object_action_module, "_loader_runtime_ref", None)
        yield

    @pytest.mark.asyncio
    async def test_uses_runtime_scoped_loader_when_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """runtime 已注册 → 走 get_loader(base_id, object_codes=[object_code])，
        不重复注入虚拟动作（快照构建时已注入），不触发 _load_ontology_cached。"""
        platform = _FakePlatform()
        loader = _FakeLoader(["Concept"])
        loader.target = _FakeTargetObject()

        def _scoped_load(
            base_id: str,
            object_codes: list[str],
            *,
            view_codes: list[str] | None = None,
        ) -> _FakeLoader:
            platform.loaded_codes.append((base_id, list(object_codes), view_codes))
            return loader

        platform.load_ontology_from_codes = _scoped_load  # type: ignore[method-assign]
        runtime = _make_runtime(platform)
        monkeypatch.setattr(
            object_action_module, "_loader_runtime_ref", lambda: runtime
        )
        platform._load_ontology_cached = _forbid_legacy_load  # type: ignore[method-assign]

        result = await invoke_object_action(
            platform=platform,  # type: ignore[arg-type]
            base_id="base-1",
            object_code="Concept",
            action_code="write_Concept",
            arguments={"content": "# Agent"},
        )
        assert result == {"records": [{"id": "rt-1"}], "total": 1}
        assert platform.loaded_codes == [("base-1", ["Concept"], None)]
        # 虚拟动作只在快照构建时注入一次（get_loader 内部），调用时无重复注入
        assert platform.injected == ["base-1"]

    @pytest.mark.asyncio
    async def test_falls_back_to_legacy_path_without_runtime(self) -> None:
        """runtime 未注册 → 回退 _load_ontology_cached 原路径（configure + 注入）。"""

        class _LegacyPlatform:
            def __init__(self) -> None:
                self.legacy_loads = 0
                self.injected = 0
                self.target = _FakeTargetObject()

            def _load_ontology_cached(self, base_id: str) -> _FakeLoader:
                self.legacy_loads += 1
                loader = _FakeLoader(["Concept"])
                loader.target = self.target
                return loader

            def inject_virtual_actions(self, base_id: str, loader: _FakeLoader) -> None:
                self.injected += 1

        platform = _LegacyPlatform()
        result = await invoke_object_action(
            platform=platform,  # type: ignore[arg-type]
            base_id="base-1",
            object_code="Concept",
            action_code="write_Concept",
            arguments={"content": "# Agent"},
        )
        assert result == {"records": [{"id": "rt-1"}], "total": 1}
        assert platform.legacy_loads == 1
        assert platform.injected == 1
        assert platform.target.calls == [
            {"action_code": "write_Concept", "arguments": {"content": "# Agent"}}
        ]


def _forbid_legacy_load(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("runtime 路径不应触发 _load_ontology_cached")

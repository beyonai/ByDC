from __future__ import annotations

from datacloud_platform.config import Settings
from datacloud_platform.loader_runtime import LoaderRuntimeManager


def _build_runtime(mode: str) -> LoaderRuntimeManager:
    settings = Settings.model_validate(
        {
            "DATACLOUD_ONTOLOGY_PATH": "packages/datacloud-platform/src/datacloud_platform/resource",
            "DATACLOUD_LOADER_MODE": mode,
        }
    )
    return LoaderRuntimeManager(settings=settings)


def test_loader_mode_static_disables_reload_and_watch() -> None:
    runtime = _build_runtime("static")

    assert runtime._should_reload() is False
    assert runtime._should_watch() is False


def test_loader_mode_lazy_enables_reload_without_watch() -> None:
    runtime = _build_runtime("lazy")

    assert runtime._should_reload() is True
    assert runtime._should_watch() is False


def test_loader_mode_watch_enables_reload_and_watch() -> None:
    runtime = _build_runtime("watch")

    assert runtime._should_reload() is True
    assert runtime._should_watch() is True

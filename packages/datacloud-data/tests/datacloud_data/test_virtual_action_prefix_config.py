"""虚拟工具前缀配置项的单元测试。

覆盖《优化方案》7.2 节用例：
UC-P1（默认值）、UC-P2（自定义前缀）、UC-P3（空前缀）、UC-P4（空白拒绝）。
"""

from __future__ import annotations

import pytest
from datacloud_data_service.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """每个用例前后清缓存，避免 lru_cache 串味。"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestVirtualActionPrefixDefaults:
    """UC-P1：未设环境变量时默认前缀为 query_ / compute_。"""

    def test_default_query_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", raising=False)
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", raising=False)
        get_settings.cache_clear()
        s = get_settings()
        assert s.virtual_action_query_prefix == "query_"

    def test_default_compute_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", raising=False)
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", raising=False)
        get_settings.cache_clear()
        s = get_settings()
        assert s.virtual_action_compute_prefix == "compute_"


class TestVirtualActionPrefixOverride:
    """UC-P2：环境变量覆盖默认值。"""

    def test_query_prefix_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", "qry_")
        get_settings.cache_clear()
        s = get_settings()
        assert s.virtual_action_query_prefix == "qry_"

    def test_compute_prefix_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", "calc_")
        get_settings.cache_clear()
        s = get_settings()
        assert s.virtual_action_compute_prefix == "calc_"

    def test_both_prefixes_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", "Q-")
        monkeypatch.setenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", "C-")
        get_settings.cache_clear()
        s = get_settings()
        assert s.virtual_action_query_prefix == "Q-"
        assert s.virtual_action_compute_prefix == "C-"


class TestVirtualActionPrefixEmpty:
    """UC-P3：空字符串前缀被允许，等价"裸工具名"。"""

    def test_empty_query_prefix_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", "")
        get_settings.cache_clear()
        s = get_settings()
        assert s.virtual_action_query_prefix == ""

    def test_empty_compute_prefix_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", "")
        get_settings.cache_clear()
        s = get_settings()
        assert s.virtual_action_compute_prefix == ""


class TestVirtualActionPrefixWhitespaceRejected:
    """UC-P4：含空白字符的前缀必须被拒绝。"""

    @pytest.mark.parametrize("bad_prefix", ["qry _", " qry", "qry\t_", "qry\n_"])
    def test_whitespace_query_prefix_rejected(
        self, monkeypatch: pytest.MonkeyPatch, bad_prefix: str
    ) -> None:
        monkeypatch.setenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", bad_prefix)
        get_settings.cache_clear()
        with pytest.raises(ValueError):
            Settings()

    @pytest.mark.parametrize("bad_prefix", ["calc _", " calc", "calc\t"])
    def test_whitespace_compute_prefix_rejected(
        self, monkeypatch: pytest.MonkeyPatch, bad_prefix: str
    ) -> None:
        monkeypatch.setenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", bad_prefix)
        get_settings.cache_clear()
        with pytest.raises(ValueError):
            Settings()

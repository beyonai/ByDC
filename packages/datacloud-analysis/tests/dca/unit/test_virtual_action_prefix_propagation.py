"""虚拟工具前缀外化在提示词与插件层的传播测试。

覆盖《优化方案》7.2 节用例：
UC-P6（query_clarification_plugin._data_tool_prefixes）、
UC-P7（中文提示词同步）、
UC-P8（英文提示词同步）、
UC-P9（默认前缀提示词等同改造前）。
"""

from __future__ import annotations

import pytest
from datacloud_analysis.i18n.prompts import (
    _get_query_tool_hint_en,
    _get_query_tool_hint_zh,
)
from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    _data_tool_prefixes,
    _is_data_tool,
    _is_query_or_compute_tool,
    _scope_code_from_tool,
)
from datacloud_data_service.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestPromptsDefaultUnchanged:
    """UC-P9：未设环境变量时，提示词与改造前完全一致。"""

    def test_zh_hint_default_contains_query_compute_examples(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", raising=False)
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", raising=False)
        get_settings.cache_clear()

        text = _get_query_tool_hint_zh()
        assert "query_{对象编码}" in text
        assert "query_ads_enterprise_analysis" in text
        assert "compute_{对象编码}" in text
        assert "compute_ads_enterprise_analysis" in text
        assert "直接调用 query 或 compute" in text

    def test_en_hint_default_contains_query_compute_examples(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", raising=False)
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", raising=False)
        get_settings.cache_clear()

        text = _get_query_tool_hint_en()
        assert "query_{object_code}" in text
        assert "query_ads_enterprise_analysis" in text
        assert "compute_{object_code}" in text
        assert "compute_ads_enterprise_analysis" in text
        assert "'query' or 'compute'" in text


class TestPromptsCustomPrefix:
    """UC-P7 / UC-P8：自定义前缀后提示词中的工具名引用全部替换。"""

    def _setenv(self, mp: pytest.MonkeyPatch, q: str, c: str) -> None:
        mp.setenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", q)
        mp.setenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", c)
        get_settings.cache_clear()

    def test_zh_hint_with_custom_prefixes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setenv(monkeypatch, "qry_", "calc_")

        text = _get_query_tool_hint_zh()
        assert "qry_{对象编码}" in text
        assert "qry_ads_enterprise_analysis" in text
        assert "calc_{对象编码}" in text
        assert "calc_ads_enterprise_analysis" in text
        # 旧字面量必须消失
        assert "query_{对象编码}" not in text
        assert "compute_{对象编码}" not in text
        # 裸名提示采用 rstrip("_") 后的形态
        assert "直接调用 qry 或 calc" in text

    def test_en_hint_with_custom_prefixes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setenv(monkeypatch, "qry_", "calc_")

        text = _get_query_tool_hint_en()
        assert "qry_{object_code}" in text
        assert "calc_{object_code}" in text
        assert "query_{object_code}" not in text
        assert "compute_{object_code}" not in text
        assert "'qry' or 'calc'" in text

    def test_zh_hint_with_empty_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """UC-P3 衍生：空前缀仍能正确渲染（rstrip("_") 回退到空串）。"""
        self._setenv(monkeypatch, "", "")
        text = _get_query_tool_hint_zh()
        # 不抛异常 + 不包含旧字面量
        assert "query_{对象编码}" not in text
        assert "compute_{对象编码}" not in text


class TestQueryClarificationPluginPrefixSync:
    """UC-P6：插件按当前 settings 识别动态工具。"""

    def _setenv(self, mp: pytest.MonkeyPatch, q: str, c: str) -> None:
        mp.setenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", q)
        mp.setenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", c)
        get_settings.cache_clear()

    def test_data_tool_prefixes_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", raising=False)
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", raising=False)
        get_settings.cache_clear()

        prefixes = _data_tool_prefixes()
        assert "query_" in prefixes
        assert "compute_" in prefixes
        assert "data_query_" in prefixes  # data_query_ 不可被外化丢失

    def test_data_tool_prefixes_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setenv(monkeypatch, "qry_", "calc_")
        prefixes = _data_tool_prefixes()
        assert "qry_" in prefixes
        assert "calc_" in prefixes
        assert "data_query_" in prefixes
        # 旧字面量不再出现
        assert "query_" not in prefixes
        assert "compute_" not in prefixes

    def test_is_query_or_compute_tool_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", raising=False)
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", raising=False)
        get_settings.cache_clear()
        assert _is_query_or_compute_tool("query_ads_enterprise") is True
        assert _is_query_or_compute_tool("compute_ads_enterprise") is True
        assert _is_query_or_compute_tool("data_query_xxx") is False
        assert _is_query_or_compute_tool("read_file") is False

    def test_is_query_or_compute_tool_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setenv(monkeypatch, "qry_", "calc_")
        assert _is_query_or_compute_tool("qry_ads_enterprise") is True
        assert _is_query_or_compute_tool("calc_ads_enterprise") is True
        assert _is_query_or_compute_tool("query_ads_enterprise") is False
        assert _is_query_or_compute_tool("compute_ads_enterprise") is False

    def test_is_data_tool_keeps_data_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setenv(monkeypatch, "qry_", "calc_")
        assert _is_data_tool("data_query_anything") is True
        assert _is_data_tool("qry_anything") is True
        assert _is_data_tool("calc_anything") is True
        assert _is_data_tool("query_anything") is False

    def test_scope_code_strips_custom_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setenv(monkeypatch, "qry_", "calc_")
        assert _scope_code_from_tool("qry_ads_foo") == "ads_foo"
        assert _scope_code_from_tool("calc_ads_foo") == "ads_foo"

    def test_scope_code_strips_default_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX", raising=False)
        monkeypatch.delenv("DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX", raising=False)
        get_settings.cache_clear()
        assert _scope_code_from_tool("query_ads_foo") == "ads_foo"
        assert _scope_code_from_tool("compute_ads_foo") == "ads_foo"

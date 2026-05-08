import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def _load_module(module_name: str, relative_path: str) -> ModuleType:
    module_path = _SRC_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_exceptions = _load_module(
    "datacloud_data_sdk.exceptions",
    "datacloud_data_sdk/exceptions.py",
)
_term_loader = _load_module(
    "datacloud_data_sdk.ontology.term_loader",
    "datacloud_data_sdk/ontology/term_loader.py",
)

TermNotFoundError = _exceptions.TermNotFoundError
KbTermLoader = _term_loader.KbTermLoader
TermLoader = _term_loader.TermLoader


def test_resolve_by_label() -> None:
    loader = KbTermLoader(
        {"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": ["签了合同"]}]}
    )
    assert loader.resolve_code("bo_stage", "已签约") == "SIGNED"


def test_resolve_by_alias() -> None:
    loader = KbTermLoader(
        {"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": ["签了合同"]}]}
    )
    assert loader.resolve_code("bo_stage", "签了合同") == "SIGNED"


def test_resolve_by_exact_code() -> None:
    loader = KbTermLoader({"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": []}]})
    assert loader.resolve_code("bo_stage", "SIGNED") == "SIGNED"


def test_resolve_unknown_raises() -> None:
    mock_result = MagicMock()
    mock_result.items = []
    with patch(
        "datacloud_data_sdk.ontology.term_loader.search_terms_by_type",
        return_value=mock_result,
    ):
        loader = KbTermLoader({"bo_stage": []})
        with pytest.raises(TermNotFoundError, match="不存在"):
            loader.resolve_code("bo_stage", "不存在的值")


def test_get_available_values() -> None:
    loader = KbTermLoader({"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": []}]})
    available = loader.get_available_values("bo_stage")
    assert "已签约" in available


def test_kb_term_loader_supports_mapping() -> None:
    loader = KbTermLoader({"bo_stage": [{"code": "SIGNED", "label": "已签约"}]})
    assert isinstance(loader, KbTermLoader)


def test_term_loader_from_config_rejects_removed_api_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported term loader type: api"):
        TermLoader.from_config({"type": "api"})


def test_kb_term_loader_from_config() -> None:
    loader = TermLoader.from_config({"type": "kb", "kb": {}})
    assert isinstance(loader, KbTermLoader)


def test_kb_term_loader_resolve_by_label() -> None:
    mock_result = MagicMock()
    mock_result.items = [
        MagicMock(term_code="SIGNED", term_name="已签约", term_tags={"synonyms": "签了合同"}),
    ]
    with patch(
        "datacloud_data_sdk.ontology.term_loader.search_terms_by_type",
        return_value=mock_result,
    ) as mock_search:
        loader = KbTermLoader()
        code = loader.resolve_code("bo_stage", "已签约")
        assert code == "SIGNED"
        mock_search.assert_called_once_with(
            term_type_code="bo_stage",
            keyword="已签约",
            limit=100,
        )


def test_kb_term_loader_resolve_by_alias() -> None:
    mock_result = MagicMock()
    mock_result.items = [
        MagicMock(term_code="SIGNED", term_name="已签约", term_tags={"synonyms": "签了合同"}),
    ]
    with patch(
        "datacloud_data_sdk.ontology.term_loader.search_terms_by_type",
        return_value=mock_result,
    ):
        loader = KbTermLoader()
        code = loader.resolve_code("bo_stage", "签了合同")
        assert code == "SIGNED"


def test_kb_term_loader_resolve_unknown_raises() -> None:
    mock_result = MagicMock()
    mock_result.items = []
    with patch(
        "datacloud_data_sdk.ontology.term_loader.search_terms_by_type",
        return_value=mock_result,
    ):
        loader = KbTermLoader()
        with pytest.raises(TermNotFoundError, match="不存在"):
            loader.resolve_code("bo_stage", "不存在")


def test_kb_term_loader_get_available_values() -> None:
    mock_result = MagicMock()
    mock_result.items = [
        MagicMock(term_code="SIGNED", term_name="已签约", term_tags={}),
        MagicMock(term_code="PENDING", term_name="待签约", term_tags={}),
    ]
    with patch(
        "datacloud_data_sdk.ontology.term_loader.search_terms_by_type",
        return_value=mock_result,
    ):
        loader = KbTermLoader()
        values = loader.get_available_values("bo_stage")
        assert "已签约" in values
        assert "待签约" in values


def test_kb_term_loader_get_codes() -> None:
    mock_result = MagicMock()
    mock_result.items = [
        MagicMock(term_code="SIGNED", term_name="已签约", term_tags={}),
    ]
    with patch(
        "datacloud_data_sdk.ontology.term_loader.search_terms_by_type",
        return_value=mock_result,
    ):
        loader = KbTermLoader()
        codes = loader.get_codes("bo_stage")
        assert "SIGNED" in codes


def test_kb_term_loader_resolve_code_explicit_type() -> None:
    mock_result = MagicMock()
    mock_result.items = [
        MagicMock(term_code="REGION_CODE", term_name="华北", term_tags={}),
    ]
    with patch(
        "datacloud_data_sdk.ontology.term_loader.search_terms_by_type",
        return_value=mock_result,
    ) as mock_search:
        loader = KbTermLoader()
        code = loader.resolve_code("region.province", "华北", term_type_code="region")
        assert code == "REGION_CODE"
        mock_search.assert_called_once_with(
            term_type_code="region",
            keyword="华北",
            limit=100,
        )


def test_resolve_value_to_code() -> None:
    loader = KbTermLoader({"staffName": [{"code": "EMP001", "label": "张三", "aliases": ["小张"]}]})
    result = loader.resolve_value("staffName", "张三", term_field="code")
    assert result == "EMP001"


def test_resolve_value_to_name() -> None:
    loader = KbTermLoader({"staffName": [{"code": "EMP001", "label": "张三", "aliases": ["小张"]}]})
    result = loader.resolve_value("staffName", "EMP001", term_field="name")
    assert result == "张三"


def test_resolve_value_default_to_code() -> None:
    loader = KbTermLoader({"staffName": [{"code": "EMP001", "label": "张三", "aliases": ["小张"]}]})
    result = loader.resolve_value("staffName", "张三", term_field=None)
    assert result == "EMP001"


def test_resolve_value_by_alias_to_name() -> None:
    loader = KbTermLoader({"staffName": [{"code": "EMP001", "label": "张三", "aliases": ["小张"]}]})
    result = loader.resolve_value("staffName", "小张", term_field="name")
    assert result == "张三"


def test_kb_resolve_value_to_code() -> None:
    mock_result = MagicMock()
    mock_result.items = [
        MagicMock(term_code="EMP001", term_name="张三", term_tags={"synonyms": "小张"}),
    ]
    with patch(
        "datacloud_data_sdk.ontology.term_loader.search_terms_by_type",
        return_value=mock_result,
    ):
        loader = KbTermLoader()
        result = loader.resolve_value("staffName", "张三", term_field="code")
        assert result == "EMP001"


def test_kb_resolve_value_to_name() -> None:
    mock_result = MagicMock()
    mock_result.items = [
        MagicMock(term_code="EMP001", term_name="张三", term_tags={"synonyms": "小张"}),
    ]
    with patch(
        "datacloud_data_sdk.ontology.term_loader.search_terms_by_type",
        return_value=mock_result,
    ):
        loader = KbTermLoader()
        result = loader.resolve_value("staffName", "EMP001", term_field="name")
        assert result == "张三"


def test_kb_term_loader_cache_isolated_by_keyword_for_resolve_code() -> None:
    first_result = MagicMock()
    first_result.items = [
        MagicMock(term_code="EMP001", term_name="张三", term_tags={"synonyms": "小张"}),
    ]
    second_result = MagicMock()
    second_result.items = [
        MagicMock(term_code="EMP002", term_name="李四", term_tags={"synonyms": "小李"}),
    ]

    with patch(
        "datacloud_data_sdk.ontology.term_loader.search_terms_by_type",
        side_effect=[first_result, second_result],
    ) as mock_search:
        loader = KbTermLoader()

        assert loader.resolve_code("staffName", "张三") == "EMP001"
        assert loader.resolve_code("staffName", "李四") == "EMP002"

        assert mock_search.call_count == 2
        mock_search.assert_any_call(term_type_code="staffName", keyword="张三", limit=100)
        mock_search.assert_any_call(term_type_code="staffName", keyword="李四", limit=100)


def test_kb_term_loader_cache_isolated_by_keyword_for_resolve_value() -> None:
    first_result = MagicMock()
    first_result.items = [
        MagicMock(term_code="EMP001", term_name="张三", term_tags={"synonyms": "小张"}),
    ]
    second_result = MagicMock()
    second_result.items = [
        MagicMock(term_code="EMP002", term_name="李四", term_tags={"synonyms": "小李"}),
    ]

    with patch(
        "datacloud_data_sdk.ontology.term_loader.search_terms_by_type",
        side_effect=[first_result, second_result],
    ) as mock_search:
        loader = KbTermLoader()

        assert loader.resolve_value("staffName", "EMP001", term_field="name") == "张三"
        assert loader.resolve_value("staffName", "EMP002", term_field="name") == "李四"

        assert mock_search.call_count == 2
        mock_search.assert_any_call(term_type_code="staffName", keyword="EMP001", limit=100)
        mock_search.assert_any_call(term_type_code="staffName", keyword="EMP002", limit=100)

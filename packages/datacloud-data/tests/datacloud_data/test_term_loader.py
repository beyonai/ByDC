from unittest.mock import MagicMock, patch

import pytest

from datacloud_data_sdk.exceptions import TermNotFoundError
from datacloud_data_sdk.ontology.term_loader import (
    ApiTermLoader,
    KbTermLoader,
    TermLoader,
)


def test_resolve_by_label() -> None:
    loader = TermLoader.from_mapping(
        {"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": ["签了合同"]}]}
    )
    assert loader.resolve_code("bo_stage", "已签约") == "SIGNED"


def test_resolve_by_alias() -> None:
    loader = TermLoader.from_mapping(
        {"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": ["签了合同"]}]}
    )
    assert loader.resolve_code("bo_stage", "签了合同") == "SIGNED"


def test_resolve_by_exact_code() -> None:
    loader = TermLoader.from_mapping(
        {"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": []}]}
    )
    assert loader.resolve_code("bo_stage", "SIGNED") == "SIGNED"


def test_resolve_unknown_raises() -> None:
    loader = TermLoader.from_mapping({"bo_stage": []})
    with pytest.raises(TermNotFoundError, match="不存在"):
        loader.resolve_code("bo_stage", "不存在的值")


def test_get_available_values() -> None:
    loader = TermLoader.from_mapping(
        {"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": []}]}
    )
    available = loader.get_available_values("bo_stage")
    assert "已签约" in available


def test_api_term_loader_from_config() -> None:
    loader = TermLoader.from_config({
        "type": "api",
        "api": {"base_url": "http://example.com", "mapping": {}},
    })
    assert isinstance(loader, ApiTermLoader)


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
            term_type_code="bo_stage", keyword="已签约", limit=100,
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
            term_type_code="region", keyword="华北", limit=100,
        )


def test_resolve_value_to_code() -> None:
    loader = TermLoader.from_mapping(
        {"staffName": [{"code": "EMP001", "label": "张三", "aliases": ["小张"]}]}
    )
    result = loader.resolve_value("staffName", "张三", term_field="code")
    assert result == "EMP001"


def test_resolve_value_to_name() -> None:
    loader = TermLoader.from_mapping(
        {"staffName": [{"code": "EMP001", "label": "张三", "aliases": ["小张"]}]}
    )
    result = loader.resolve_value("staffName", "EMP001", term_field="name")
    assert result == "张三"


def test_resolve_value_default_to_code() -> None:
    loader = TermLoader.from_mapping(
        {"staffName": [{"code": "EMP001", "label": "张三", "aliases": ["小张"]}]}
    )
    result = loader.resolve_value("staffName", "张三", term_field=None)
    assert result == "EMP001"


def test_resolve_value_by_alias_to_name() -> None:
    loader = TermLoader.from_mapping(
        {"staffName": [{"code": "EMP001", "label": "张三", "aliases": ["小张"]}]}
    )
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

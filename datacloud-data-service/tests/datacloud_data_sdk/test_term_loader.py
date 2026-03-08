import pytest
from datacloud_data_sdk.ontology.term_loader import TermLoader


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
    with pytest.raises(ValueError, match="available"):
        loader.resolve_code("bo_stage", "不存在的值")


def test_get_available_values() -> None:
    loader = TermLoader.from_mapping(
        {"bo_stage": [{"code": "SIGNED", "label": "已签约", "aliases": []}]}
    )
    available = loader.get_available_values("bo_stage")
    assert "已签约" in available

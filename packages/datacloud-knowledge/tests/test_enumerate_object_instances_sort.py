"""SortSpec 类型形状 + enumerate_object_instances 协议签名（sort 条件框架）。

本层仅签名验收：
- SortSpec 形状 {by: str, params: dict}（与 FilterSpec 请求元素同构），by 目前仅 "similarity"
- TermReader 协议 / provider 入口签名新增 ``sort: dict[str, Any] | None = None``
- 返回模型 ObjectInstanceItem 保持 6 字段，不加 score（verify gate 钉死）
- 不改 total 语义、不建 _SORT_REGISTRY、不启用 embedding 实际逻辑

注意：本层只验形状与签名，不验 SQL 排序行为（EmbeddingService 落地）。
"""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, fields
from typing import Any, get_type_hints
from unittest.mock import Mock, patch

import pytest
from datacloud_knowledge import provider
from datacloud_knowledge.contracts.protocols import TermReader
from datacloud_knowledge.contracts.term_provider_types import (
    EnumeratedObjectInstances,
    ObjectInstanceItem,
    SortSpec,
)

# ═════════════════════════════════════════════════════════════════════════════
# 1. SortSpec 类型形状
# ═════════════════════════════════════════════════════════════════════════════


def test_sort_spec_shape_has_by_and_params() -> None:
    """SortSpec 形状 = {by: str, params: dict}，params 缺省为空 dict。"""
    spec = SortSpec(by="similarity")
    assert spec.by == "similarity"
    assert spec.params == {}
    assert isinstance(spec.params, dict)


def test_sort_spec_is_frozen() -> None:
    """与 FilterSpec 同构：frozen dataclass（注册表条目可哈希，防意外变更）。"""
    spec = SortSpec(by="similarity")
    with pytest.raises(FrozenInstanceError):
        spec.by = "other"


def test_sort_spec_by_only_allows_similarity() -> None:
    """by 目前仅 "similarity"（类型层面 Literal 约束，后续扩展时放宽）。"""
    hints = get_type_hints(SortSpec)
    assert "similarity" in str(hints["by"])


# ═════════════════════════════════════════════════════════════════════════════
# 2. 协议 / 入口签名含 sort
# ═════════════════════════════════════════════════════════════════════════════


def test_term_reader_protocol_accepts_sort() -> None:
    """TermReader.enumerate_object_instances 签名新增 sort，默认 None。"""
    params = inspect.signature(TermReader.enumerate_object_instances).parameters
    assert "sort" in params
    sort_param = params["sort"]
    assert sort_param.default is None
    assert sort_param.kind == inspect.Parameter.KEYWORD_ONLY


def test_provider_entry_accepts_sort() -> None:
    """provider.enumerate_object_instances 签名新增 sort，默认 None。"""
    params = inspect.signature(provider.enumerate_object_instances).parameters
    assert "sort" in params
    sort_param = params["sort"]
    assert sort_param.default is None
    assert sort_param.kind == inspect.Parameter.KEYWORD_ONLY


def test_provider_forwards_sort_to_reader() -> None:
    """provider 入口将 sort 原样透传给 reader（本层仅签名，不做解析）。"""
    reader = Mock()
    reader.enumerate_object_instances.return_value = EnumeratedObjectInstances(items=[], total=0)
    sort: dict[str, Any] = {"by": "similarity", "params": {}}
    with patch("datacloud_knowledge.provider.create_reader", return_value=reader):
        provider.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=["kb1"],
            sort=sort,
        )
    kwargs = reader.enumerate_object_instances.call_args.kwargs
    assert kwargs["sort"] is sort


# ═════════════════════════════════════════════════════════════════════════════
# 3. 返回模型不变（verify gate：不加 score、不改 total 语义）
# ═════════════════════════════════════════════════════════════════════════════


def test_object_instance_item_keeps_six_fields_no_score() -> None:
    """ObjectInstanceItem 保持 6 字段，不得新增 score（verify gate 钉死）。"""
    names = [f.name for f in fields(ObjectInstanceItem)]
    assert names == [
        "term_id",
        "term_code",
        "term_name",
        "term_type_code",
        "out_degree",
        "in_degree",
    ]
    assert "score" not in names


def test_enumerated_envelope_unchanged() -> None:
    """信封保持 items + total 两字段，total 语义不动。"""
    names = [f.name for f in fields(EnumeratedObjectInstances)]
    assert names == ["items", "total"]

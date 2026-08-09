"""全量回归 + 签名同步完整性（详见 signature_sync 文件）。

覆盖：
  A 点 resolve_fragment_term_details：以现状参数调用（label_filters +
        label_condition="or" + term_type_codes + top_k=200）→ 调用形态与输出
        与改造前一致（mock 断言）。
  C 点 _match_chunks_to_terms_by_filepath：label_filters OR 组 +
        term_type_codes + top_k*N 调用形态不变，输出不变。
  透传链 mixins/term.py：**kwargs 透传到 backend（含新参数）不变。
  remote / none 占位：签名接受新参数，行为仍返回 []。
  异常兜底：底层 DB 不可达 → [] 不抛（含新参数路径）。
  term_type_codes / top_k 语义回归（已由行为/LIMIT 用例覆盖，此处补 DB 不可达
        不抛与 label 非空形态等价）。

等价性基准：改造仅涉及底层 SQL 组装与 B 点调用形态；A/C 点调用代码零改动，
本测试用 mock 断言「调用参数形态 + 输出映射」与改造前一致。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from datacloud_knowledge.adapters.opengauss._readers import _base as _reader_base
from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
from datacloud_platform.adapters.data_adapter._ontology_metadata import (
    OntologyMetadataMixin,
)
from datacloud_platform.adapters.none_adapters import _NoopTermBackend
from datacloud_platform.adapters.remote_adapter import RemoteTermBackend
from datacloud_platform.mixins.document import resolve_fragment_term_details
from datacloud_platform.mixins.term import TermMixin


# ═════════════════════════════════════════════════════════════════════════════
# T9-1 [P1] A 点 resolve_fragment_term_details 零回归
# ═════════════════════════════════════════════════════════════════════════════


def test_t9_a_point_call_shape_and_output_unchanged() -> None:
    """A 点以现状参数形态调用；输出逐项一致。"""
    platform = Mock()
    platform.search_terms_by_labels.return_value = [
        {
            "term_id": "t1",
            "term_code": "C1",
            "term_name": "头痛",
            "term_type_code": "T1",
            "term_tags": {"kb_file_path": "/a/p1.md"},
            "ext_attrs": {"kb_resource_id": "r1", "kb_id": "k1"},
            "score": 1.0,
        }
    ]
    fragment_rows = (
        {"resourceId": "r1", "filePath": "/a/p1.md", "score": 0.9},
        {"resourceId": "r2", "filePath": "/b/p1.md", "score": 0.8},
    )
    details = resolve_fragment_term_details(
        platform=platform,
        base_id="base-1",
        fragment_rows=fragment_rows,
        object_codes=("T1",),
    )
    # 调用形态：label_filters OR 组 + term_type_codes + top_k=200（现状不变）
    platform.search_terms_by_labels.assert_called_once()
    kwargs = platform.search_terms_by_labels.call_args.kwargs
    # candidate_keys 来自 set，label_filters 顺序不保证（现状行为）→ 按集合断言
    lf_values = {lf["filter_value"] for lf in kwargs["label_filters"]}
    assert lf_values == {"/a/p1.md", "/b/p1.md"}
    assert all(lf["field_code"] == "kb_file_path" for lf in kwargs["label_filters"])
    assert len(kwargs["label_filters"]) == 2
    assert kwargs["label_condition"] == "or"
    assert kwargs["term_type_codes"] == ["T1"]
    assert kwargs["top_k"] == 200
    # 输出逐项一致
    assert details == {
        ("r1", "/a/p1.md"): {
            "termId": "t1",
            "termCode": "C1",
            "termName": "头痛",
            "objectCode": "T1",
        }
    }


# ═════════════════════════════════════════════════════════════════════════════
# T9-2 [P1] C 点 _match_chunks_to_terms_by_filepath 零回归
# ═════════════════════════════════════════════════════════════════════════════


def test_t9_c_point_call_shape_and_output_unchanged() -> None:
    """C 点 label_filters OR 组 + term_type_codes + top_k*N 形态不变，输出不变。"""
    host = OntologyMetadataMixin.__new__(OntologyMetadataMixin)  # type: ignore[call-arg]
    calls: list[dict[str, Any]] = []

    def _fake_search(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [
            {
                "term_id": "t1",
                "term_code": "C1",
                "term_name": "合同",
                "term_type_code": "T2",
                "term_tags": {},
                "ext_attrs": {"kb_file_path": "/a/p1.md"},
                "score": 0.9,
            }
        ]

    host.search_terms_by_labels = _fake_search  # type: ignore[method-assign]
    result = OntologyMetadataMixin._match_chunks_to_terms_by_filepath(
        host,
        file_scores={"/a/p1.md": 0.9, "/b/p1.md": 0.8},
        top_k=1,
        term_type_codes=["T2"],
    )
    assert calls == [
        {
            "label_filters": [
                {"field_code": "kb_file_path", "filter_value": "/a/p1.md"},
                {"field_code": "kb_file_path", "filter_value": "/b/p1.md"},
            ],
            "label_condition": "or",
            "term_type_codes": ["T2"],
            "top_k": 2,  # top_k * len(file_scores)
        }
    ]
    # 输出：按 score 排序后截断 top_k=1
    assert result == [
        {
            "term_id": "t1",
            "term_code": "C1",
            "term_name": "合同",
            "term_type_code": "T2",
            "file_name": "/a/p1.md",
            "match_type": "chunk_to_term",
            "score": 0.9,
        }
    ]


# ═════════════════════════════════════════════════════════════════════════════
# T9-3 [P1] 透传链 mixins/term.py 回归（**kwargs 透传含 filters）
# ═════════════════════════════════════════════════════════════════════════════


def test_t9_mixin_term_passthrough_with_filters() -> None:
    """TermMixin.search_terms_by_labels 将 filters 原样透传到 backend。"""

    class _RecordingBackend:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def search_terms_by_labels(self, **kwargs: Any) -> list[dict[str, Any]]:
            self.calls.append(kwargs)
            return []

    class _P(TermMixin):
        def __init__(self) -> None:
            self._backend = _RecordingBackend()

        def _term_for(self, base_id: str) -> Any:  # pragma: no cover - 测试桩
            return self._backend

    p = _P()
    result = p.search_terms_by_labels(
        "base-1",
        label_filters=None,
        filters=[
            {"field": "kb_id", "op": "in", "values": ["k1"]},
            {"field": "kb_resource_id", "op": "in", "values": ["r1"]},
            {"field": "kb_file_path", "op": "in", "values": ["/a/p1.md"]},
        ],
        top_k=3000,
    )
    assert result == []
    assert p._backend.calls == [
        {
            "label_filters": None,
            "filters": [
                {"field": "kb_id", "op": "in", "values": ["k1"]},
                {"field": "kb_resource_id", "op": "in", "values": ["r1"]},
                {"field": "kb_file_path", "op": "in", "values": ["/a/p1.md"]},
            ],
            "top_k": 3000,
        }
    ]


# ═════════════════════════════════════════════════════════════════════════════
# T9-4 [P1] remote / none 占位回归（签名接受 filters，行为仍 []）
# ═════════════════════════════════════════════════════════════════════════════


def test_t9_remote_placeholder_returns_empty_with_filters() -> None:
    backend = RemoteTermBackend.__new__(RemoteTermBackend)  # type: ignore[call-arg]
    result = backend.search_terms_by_labels(  # type: ignore[attr-defined]
        label_filters=None,
        filters=[
            {"field": "kb_id", "op": "in", "values": ["k1"]},
            {"field": "kb_resource_id", "op": "in", "values": ["r1"]},
            {"field": "kb_file_path", "op": "in", "values": ["/a/p1.md"]},
        ],
        term_type_codes=["T1"],
        top_k=3000,
    )
    assert result == []


def test_t9_none_placeholder_returns_empty_with_filters() -> None:
    backend = _NoopTermBackend.__new__(_NoopTermBackend)  # type: ignore[call-arg]
    result = backend.search_terms_by_labels(  # type: ignore[attr-defined]
        label_filters=None,
        filters=[
            {"field": "kb_id", "op": "in", "values": ["k1"]},
            {"field": "kb_resource_id", "op": "in", "values": ["r1"]},
            {"field": "kb_file_path", "op": "in", "values": ["/a/p1.md"]},
        ],
        term_type_codes=["T1"],
        top_k=3000,
    )
    assert result == []


# ═════════════════════════════════════════════════════════════════════════════
# 三参数已从签名删除（inspect 反射）
# ═════════════════════════════════════════════════════════════════════════════


def test_t9_three_param_removed_from_platform_signatures() -> None:
    """platform 侧 search_terms_by_labels 签名无三参数（反射确认不存在）。"""
    import inspect

    from datacloud_platform.adapters.data_adapter._term import TermBackendMixin
    from datacloud_platform.backends.term import TermBackend

    for func in (
        TermBackendMixin.search_terms_by_labels,
        TermBackend.search_terms_by_labels,
    ):
        sig = inspect.signature(func)
        for removed in ("kb_ids", "kb_resource_ids", "kb_file_paths"):
            assert removed not in sig.parameters, (
                f"{func.__qualname__} 三参数 {removed} 未删除"
            )
        assert "filters" in sig.parameters


# ═════════════════════════════════════════════════════════════════════════════
# T9-5 [P1] 异常兜底回归：DB 不可达 → [] 不抛（含新参数路径）
# ═════════════════════════════════════════════════════════════════════════════


class _ExplodingSession:
    def __enter__(self) -> "_ExplodingSession":
        return self

    def __exit__(self, *_: Any) -> bool:
        return False

    def execute(self, *_: Any, **__: Any) -> Any:
        raise RuntimeError("db down")


def test_t9_db_unreachable_returns_empty_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """底层函数在 DB 不可达时返回 [] 不抛异常（filters 路径）。"""
    monkeypatch.setattr(_reader_base, "_SCHEMA_CHECKED", True)
    reader = PostgresTermReader(session_factory=lambda: _ExplodingSession())  # type: ignore[arg-type]
    result = reader.query_terms_by_labels(
        label_filters=None,
        filters=[
            {"field": "kb_id", "op": "in", "values": ["k1"]},
            {"field": "kb_resource_id", "op": "in", "values": ["r1"]},
            {"field": "kb_file_path", "op": "in", "values": ["/a/p1.md"]},
        ],
        top_k=3000,
    )
    assert result == []


def test_t9_db_unreachable_label_shape_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """label 非空形态（A/C 点调用形态）DB 不可达 → [] 不抛。"""
    monkeypatch.setattr(_reader_base, "_SCHEMA_CHECKED", True)
    reader = PostgresTermReader(session_factory=lambda: _ExplodingSession())  # type: ignore[arg-type]
    result = reader.query_terms_by_labels(
        label_filters=[{"field_code": "kb_file_path", "filter_value": "/a/p1.md"}],
        label_condition="or",
        term_type_codes=["T1"],
        top_k=200,
    )
    assert result == []

"""签名完整性：六处签名同步 + FilterSpec 定义导出 + mixins/term.py 未改。

断言：
  1. 底层 query_terms_by_labels 签名基准：label_filters 可选 + filters（含默认值）、
     无三参数（kb_ids / kb_resource_ids / kb_file_paths 已删除）。
  2. protocols.py / data_adapter/_term.py / backends/term.py / remote_adapter.py /
     none_adapters.py 五处签名与底层一致（参数名 + 默认值逐项一致，无三参数）。
  3. contracts/term_provider_types.py 新增 FilterSpec TypedDict（field/op/values
     三键）并导出（__all__）。
  4. mixins/term.py 的 search_terms_by_labels 未改动（**kwargs 透传仍兼容）。

注：类型标注允许存在领域差异（knowledge 侧 list[FilterSpec] / platform 侧
list[dict[str, Any]]），本测试只比对参数名 + 默认值。
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

# 唯一 SQL 实现：签名基准
from datacloud_knowledge.adapters.opengauss._readers import _term as _reader_term
from datacloud_knowledge.contracts import term_provider_types as tpt


def _param_specs(func: Any) -> list[tuple[str, Any]]:
    """提取 (参数名, 默认值) 序列；默认值用 repr 比较。"""
    sig = inspect.signature(func)
    out: list[tuple[str, Any]] = []
    for name, p in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        default = p.default if p.default is not inspect.Parameter.empty else "<required>"
        out.append((name, default))
    return out


def _load_platform_module(module_path: str) -> Any:
    """按包路径动态导入 platform 侧模块（避免 tests 目录 sys.path 差异）。"""
    import importlib

    return importlib.import_module(module_path)


# ═════════════════════════════════════════════════════════════════════════════
# 底层签名基准：无三参数 + 有 filters
# ═════════════════════════════════════════════════════════════════════════════


def test_t10_baseline_signature_shape() -> None:
    """底层 query_terms_by_labels 签名基准：label_filters 可选 + filters，无三参数。"""
    specs = _param_specs(_reader_term._TermReader.query_terms_by_labels)
    names = [name for name, _ in specs]
    assert names == [
        "label_filters",
        "label_condition",
        "term_type_codes",
        "filters",
        "top_k",
    ]
    defaults = dict(specs)
    assert defaults["label_filters"] is None
    assert defaults["label_condition"] == "or"
    assert defaults["term_type_codes"] is None
    assert defaults["filters"] is None
    assert defaults["top_k"] == 200


def test_t10_three_param_removed_from_baseline() -> None:
    """三参数已从底层签名删除（inspect 反射确认不存在）。"""
    specs = dict(_param_specs(_reader_term._TermReader.query_terms_by_labels))
    for removed in ("kb_ids", "kb_resource_ids", "kb_file_paths"):
        assert removed not in specs, f"三参数 {removed} 未删除"


@pytest.mark.parametrize(
    ("module", "cls", "member"),
    [
        (
            "datacloud_knowledge.contracts.protocols",
            "TermReader",
            "query_terms_by_labels",
        ),
        (
            "datacloud_platform.backends.term",
            "TermBackend",
            "search_terms_by_labels",
        ),
        (
            "datacloud_platform.adapters.data_adapter._term",
            "TermBackendMixin",
            "search_terms_by_labels",
        ),
        (
            "datacloud_platform.adapters.remote_adapter",
            "RemoteTermBackend",
            "search_terms_by_labels",
        ),
        (
            "datacloud_platform.adapters.none_adapters",
            "_NoopTermBackend",
            "search_terms_by_labels",
        ),
    ],
)
def test_t10_five_signatures_synced(module: str, cls: str, member: str) -> None:
    """五处转发/占位签名与底层 query_terms_by_labels 参数名+默认值一致（无三参）。"""
    mod = _load_platform_module(module)
    func = getattr(getattr(mod, cls), member)

    base = dict(_param_specs(_reader_term._TermReader.query_terms_by_labels))
    actual = dict(_param_specs(func))
    assert set(actual) == set(base), f"{module}.{cls}.{member} 参数集不一致"
    for name, value in base.items():
        assert actual[name] == value, (
            f"{module}.{cls}.{member} 参数 {name} 默认值不一致: "
            f"实际={actual[name]!r} 期望={value!r}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# FilterSpec 定义与导出
# ═════════════════════════════════════════════════════════════════════════════


def test_t10_filterspec_defined_and_exported() -> None:
    """contracts/term_provider_types.py 定义 FilterSpec TypedDict 并导出（__all__）。"""
    assert hasattr(tpt, "FilterSpec"), "FilterSpec 未在 term_provider_types 定义"
    assert "FilterSpec" in tpt.__all__, "FilterSpec 未加入 __all__ 导出"
    # 结构契约：三键必填（total=True 语义）
    annotations = tpt.FilterSpec.__annotations__
    assert set(annotations) == {"field", "op", "values"}
    required = getattr(tpt.FilterSpec, "__required_keys__", None)
    assert required is not None and required == frozenset({"field", "op", "values"})
    # op 字面量限定 eq/in
    assert "eq" in str(annotations["op"]) and "in" in str(annotations["op"])


# ═════════════════════════════════════════════════════════════════════════════
# mixins/term.py 未改动（**kwargs 透传）
# ═════════════════════════════════════════════════════════════════════════════


def test_t10_mixin_term_kwargs_transparent() -> None:
    """mixins/term.py search_terms_by_labels 未改动：**kwargs 透传（无显式参数）。"""
    from datacloud_platform.mixins import term as mixin_term

    func = mixin_term.TermMixin.search_terms_by_labels
    sig = inspect.signature(func)
    assert sig.parameters["kwargs"].kind is inspect.Parameter.VAR_KEYWORD
    explicit = [name for name, p in sig.parameters.items() if name not in ("self", "kwargs")]
    assert explicit == ["base_id"], f"mixins/term.py 出现新显式参数: {explicit}"

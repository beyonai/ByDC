"""B 点 resolve_document_objects_by_file_paths 迁移验收（filters 形态）。

覆盖：
  top_k 放大：N=3 → top_k=3000；N=15 → top_k=10000 + warning；恰好调用 1 次（循环合并）；
      调用形态 = filters 三元组（kb_id / kb_resource_id / kb_file_path，均 op=in），
      不再传 label_filters。
  等价性：filters 形态调用结果 == 三参数形态调用结果（集合等价）——等价基准 =
      mock 复刻的三参数调用（直接验证 filters ↔ 三参数映射）；结合既有等价性
      已锁定的「三参数 == HEAD 现状」形成传递闭包。陷阱行（跨组 path / 白名单外 /
      未知 kb）不放行；(kb_id, path) 跨组组合不出现。
  端到端：单 kb 组 1 path，DB 匹配 >1000 行且前 1000 行 kb_id 不匹配 →
      合并后返回非空（过滤前截断不复现）。
  空守卫：kb_resource_ids 空 / 无有效路径 → 提前 return []，不发起调用。

基建：_SqlLikePlatform 模拟底层 SQL 下推语义（filters 生效维度全 AND + LIMIT
截断在过滤后）；_ThreeParamPlatform 模拟三参数调用形态（等价基准）。
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from datacloud_platform.mixins.document import resolve_document_objects_by_file_paths

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# 基建
# ─────────────────────────────────────────────────────────────────────────────


def _md(row: dict[str, Any]) -> dict[str, Any]:
    """_term_metadata 等价：{**ext_attrs, **term_tags}（tags 覆盖 ext_attrs）。"""
    return {
        **(row.get("ext_attrs") or {}),
        **(row.get("term_tags") or {}),
    }


def _ids(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row["term_id"]) for row in rows}


def _row(term_id: str, *, kb_id: str, resource: str, path: str) -> dict[str, Any]:
    return {
        "term_id": term_id,
        "term_code": f"C-{term_id}",
        "term_name": f"名称-{term_id}",
        "term_type": "T1",
        "term_tags": {"kb_file_path": path},
        "ext_attrs": {"kb_id": kb_id, "kb_resource_id": resource},
        "score": 1.0,
    }


class _SqlLikePlatform:
    """模拟底层 SQL 下推语义：filters 生效维度全 AND + LIMIT 截断（过滤后）。

    仅实现 search_terms_by_labels 一个方法；记录每次调用参数。
    同时支持 filters 与 kb_ids 三参数两种形态（等价对比）。
    """

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def search_terms_by_labels(
        self, base_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        self.calls.append((base_id, dict(kwargs)))
        matched: list[dict[str, Any]] = []
        for row in self.rows:
            md = _md(row)
            ok = True
            # filters 形态：元素按传入序逐项 AND（eq/in 语义与底层一致）
            filters = kwargs.get("filters")
            if ok and filters:
                for flt in filters:
                    field = flt["field"]
                    op = flt["op"]
                    values = flt["values"]
                    if field == "kb_id":
                        val = str(md.get("kb_id") or "")
                    elif field == "kb_resource_id":
                        val = str(md.get("kb_resource_id") or "")
                    elif field == "kb_file_path":
                        val = str(md.get("kb_file_path") or "")
                    else:
                        raise ValueError(f"unexpected filters field: {field}")
                    if op == "in":
                        ok = ok and val in set(values)
                    elif op == "eq":
                        ok = ok and (val == str(values[0]) if values else False)
                    else:
                        raise ValueError(f"unexpected op: {op}")
            # 三参数形态（等价基准）
            kb_ids = kwargs.get("kb_ids")
            if ok and kb_ids:
                ok = str(md.get("kb_id") or "") in set(kb_ids)
            kb_resource_ids = kwargs.get("kb_resource_ids")
            if ok and kb_resource_ids:
                ok = str(md.get("kb_resource_id") or "") in set(kb_resource_ids)
            kb_file_paths = kwargs.get("kb_file_paths")
            if ok and kb_file_paths:
                ok = str(md.get("kb_file_path") or "") in set(kb_file_paths)
            if ok:
                matched.append(row)
        return matched[: kwargs.get("top_k", 200)]


class _ThreeParamPlatform:
    """仅接受三参数调用形态的 mock（等价基准 = 三参数 B 点调用形态）。"""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def search_terms_by_labels(
        self, base_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        matched: list[dict[str, Any]] = []
        for row in self.rows:
            md = _md(row)
            ok = True
            kb_ids = kwargs.get("kb_ids")
            if ok and kb_ids:
                ok = str(md.get("kb_id") or "") in set(kb_ids)
            kb_resource_ids = kwargs.get("kb_resource_ids")
            if ok and kb_resource_ids:
                ok = str(md.get("kb_resource_id") or "") in set(kb_resource_ids)
            kb_file_paths = kwargs.get("kb_file_paths")
            if ok and kb_file_paths:
                ok = str(md.get("kb_file_path") or "") in set(kb_file_paths)
            if ok:
                matched.append(row)
        return matched[: kwargs.get("top_k", 200)]


def _legacy_resolve(
    rows: list[dict[str, Any]],
    kb_resource_ids: tuple[str, ...],
    file_paths_by_kb_id: dict[str, tuple[str, ...]],
) -> list[dict[str, Any]]:
    """现状 per-kb for 循环等价实现（B 点改造前现状基准）。

    SQL 层：label_filters OR 组（path 匹配） + LIMIT 1000（过滤前截断）；
    内存层：kb_id 等值 + kb_resource_id 白名单 + path 组内校验。
    """
    out: list[dict[str, Any]] = []
    allowed_kb_resource_ids = set(kb_resource_ids)
    for kb_id, raw_file_paths in file_paths_by_kb_id.items():
        file_paths = tuple(dict.fromkeys(p for p in raw_file_paths if p))
        if not kb_id or not file_paths:
            continue
        allowed_paths = set(file_paths)
        # 现状 SQL：label_filters=[{kb_file_path: p}...] OR + LIMIT 1000
        hits = [
            row
            for row in rows
            if str((row.get("term_tags") or {}).get("kb_file_path") or "")
            in allowed_paths
        ][:1000]
        for row in hits:
            metadata = _md(row)
            if str(metadata.get("kb_id") or "") != str(kb_id):
                continue
            if str(metadata.get("kb_resource_id") or "") not in allowed_kb_resource_ids:
                continue
            if str(metadata.get("kb_file_path") or "") not in allowed_paths:
                continue
            out.append(row)
    return out


async def _resolve_v1_three_param(
    rows: list[dict[str, Any]],
    kb_resource_ids: tuple[str, ...],
    file_paths_by_kb_id: dict[str, tuple[str, ...]],
) -> list[dict[str, Any]]:
    """B 点调用形态复刻（等价基准）：三参数调用 + 内存层三条件防御校验。

    前置守卫与 top_k 放大完全一致（不变项）——唯一差异是
    platform 调用形态（kb_ids=... vs filters=[...]）。
    """
    allowed_kb_resource_ids = set(kb_resource_ids)
    if not kb_resource_ids:
        return []
    all_kb_ids = list(file_paths_by_kb_id.keys())
    all_paths = tuple(
        dict.fromkeys(p for ps in file_paths_by_kb_id.values() for p in ps if p)
    )
    if not all_kb_ids or not all_paths:
        return []
    n_groups = len(all_kb_ids)
    top_k = min(1000 * n_groups, 10000)
    platform = _ThreeParamPlatform(rows)
    result = platform.search_terms_by_labels(
        "base-1",
        kb_ids=all_kb_ids,
        kb_resource_ids=list(kb_resource_ids) or None,
        kb_file_paths=list(all_paths),
        top_k=top_k,
    )
    out: list[dict[str, Any]] = []
    for row in result:
        metadata = _md(row)
        if str(metadata.get("kb_resource_id") or "") not in allowed_kb_resource_ids:
            continue
        result_kb_id = str(metadata.get("kb_id") or "")
        if result_kb_id not in file_paths_by_kb_id:
            continue
        if (
            str(metadata.get("kb_file_path") or "")
            not in file_paths_by_kb_id[result_kb_id]
        ):
            continue
        out.append(row)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# top_k 放大规则 + 单次调用 + filters 调用形态
# ─────────────────────────────────────────────────────────────────────────────


async def test_t6_three_groups_top_k_3000_single_call() -> None:
    """N=3 组 → top_k=min(1000*3,10000)=3000，且恰好调用 1 次；filters 三元组。"""
    rows = [
        _row(f"t{i}", kb_id=f"k{i % 3}", resource="r1", path=f"/kb{i % 3}/p.md")
        for i in range(6)
    ]
    platform = _SqlLikePlatform(rows)
    file_paths_by_kb_id = {
        "k0": ("/kb0/p.md",),
        "k1": ("/kb1/p.md",),
        "k2": ("/kb2/p.md",),
    }
    result = await resolve_document_objects_by_file_paths(
        platform=platform,  # type: ignore[arg-type]
        base_id="base-1",
        kb_resource_ids=("r1",),
        file_paths_by_kb_id=file_paths_by_kb_id,
    )
    assert len(platform.calls) == 1  # 循环合并验证
    base_id, kwargs = platform.calls[0]
    assert base_id == "base-1"
    assert kwargs["top_k"] == 3000
    # 迁移：三参数 → filters 三元组（kb_id / kb_resource_id / kb_file_path，op=in）
    assert kwargs["filters"] == [
        {"field": "kb_id", "op": "in", "values": ["k0", "k1", "k2"]},
        {"field": "kb_resource_id", "op": "in", "values": ["r1"]},
        {
            "field": "kb_file_path",
            "op": "in",
            "values": ["/kb0/p.md", "/kb1/p.md", "/kb2/p.md"],
        },
    ]
    assert "kb_ids" not in kwargs  # 三参数已从调用中移除
    assert "kb_resource_ids" not in kwargs
    assert "kb_file_paths" not in kwargs
    assert "label_filters" not in kwargs  # 不再传 label_filters（依赖跳过语义）
    assert _ids(result) == {"t0", "t1", "t2", "t3", "t4", "t5"}


async def test_t6_fifteen_groups_top_k_capped_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """N=15 组 → top_k=10000（钳制）且记录 warning。"""
    rows = [
        _row(f"t{i}", kb_id=f"k{i % 15}", resource="r1", path=f"/kb{i % 15}/p.md")
        for i in range(15)
    ]
    platform = _SqlLikePlatform(rows)
    file_paths_by_kb_id = {f"k{i}": (f"/kb{i}/p.md",) for i in range(15)}
    with caplog.at_level(logging.WARNING, logger="datacloud_platform.mixins.document"):
        await resolve_document_objects_by_file_paths(
            platform=platform,  # type: ignore[arg-type]
            base_id="base-1",
            kb_resource_ids=("r1",),
            file_paths_by_kb_id=file_paths_by_kb_id,
        )
    assert len(platform.calls) == 1
    assert platform.calls[0][1]["top_k"] == 10000
    assert any(
        "钳制" in rec.message or "cap" in rec.message.lower() for rec in caplog.records
    )


# ─────────────────────────────────────────────────────────────────────────────
# 端到端：过滤前截断缺陷修复（B 点函数级）
# ─────────────────────────────────────────────────────────────────────────────


async def test_t5_merged_nonempty_where_legacy_empty() -> None:
    """单 kb 组 1 path：前 1000 行 path 匹配但 kb 不匹配 → 现状空 → 合并后非空。"""
    rows = [
        _row(f"m{i}", kb_id="other", resource="rother", path="/a/p1.md")
        for i in range(1000)
    ]
    rows += [
        _row(f"h{i}", kb_id="k1", resource="r1", path="/a/p1.md") for i in range(500)
    ]
    platform = _SqlLikePlatform(rows)
    file_paths_by_kb_id = {"k1": ("/a/p1.md",)}
    legacy = _legacy_resolve(rows, ("r1",), file_paths_by_kb_id)
    assert (
        legacy == []
    )  # 现状（per-kb for 循环 + 过滤前 LIMIT）：LIMIT 内 1000 行全被内存滤掉 → 空

    result = await resolve_document_objects_by_file_paths(
        platform=platform,  # type: ignore[arg-type]
        base_id="base-1",
        kb_resource_ids=("r1",),
        file_paths_by_kb_id=file_paths_by_kb_id,
    )
    assert len(platform.calls) == 1
    assert platform.calls[0][1]["top_k"] == 1000  # min(1000*1, 10000)
    assert len(result) == 500  # 非空：截断后移生效
    assert all(str(r["term_id"]).startswith("h") for r in result)


# ─────────────────────────────────────────────────────────────────────────────
# 等价闭包：filters 形态 == 三参数形态（集合等价 + 配对正确性）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def equiv_rows() -> list[dict[str, Any]]:
    """2 个 kb 组（k1: 2 path / k2: 1 path），含全部陷阱行。"""
    return [
        # 命中组1
        _row("r1a", kb_id="k1", resource="r1", path="/a/p1.md"),
        _row("r1b", kb_id="k1", resource="r1", path="/a/p2.md"),
        # 命中组2
        _row("r2a", kb_id="k2", resource="r2", path="/b/p1.md"),
        # 跨组陷阱：kb_id=k1 但 path 属 k2 组 → 不放行
        _row("trap-cross", kb_id="k1", resource="r1", path="/b/p1.md"),
        # kb_id=k2 组 + path 属 k2 组 + resource=r1（白名单内）→ 放行
        _row("r2b", kb_id="k2", resource="r1", path="/b/p1.md"),
        # kb_resource_id 不在白名单 → 不放行
        _row("trap-res", kb_id="k1", resource="r9", path="/a/p1.md"),
        # kb_id 不在任何组 → 不放行
        _row("trap-kb", kb_id="k3", resource="r1", path="/a/p1.md"),
    ]


async def test_t7_filters_equals_three_param_set(
    equiv_rows: list[dict[str, Any]],
) -> None:
    """filters 形态输出 == 三参数形态输出（集合等价，传递闭包）。

    结合既有「三参数 == 现状」等价性形成传递闭包
    （filters ↔ 三参数 ↔ HEAD 现状）。陷阱行不放行、(kb_id, path) 跨组不出现。
    """
    file_paths_by_kb_id = {
        "k1": ("/a/p1.md", "/a/p2.md"),
        "k2": ("/b/p1.md",),
    }
    kb_resource_ids = ("r1", "r2")

    # 三参数形态（等价基准）
    three_param = await _resolve_v1_three_param(
        equiv_rows, kb_resource_ids, file_paths_by_kb_id
    )
    assert _ids(three_param) == {"r1a", "r1b", "r2a", "r2b"}

    # filters 形态（B 点迁移后）
    platform = _SqlLikePlatform(equiv_rows)
    result = await resolve_document_objects_by_file_paths(
        platform=platform,  # type: ignore[arg-type]
        base_id="base-1",
        kb_resource_ids=kb_resource_ids,
        file_paths_by_kb_id=file_paths_by_kb_id,
    )
    # 集合等价：filters 形态 == 三参数形态
    assert _ids(result) == _ids(three_param)
    assert len(result) == len(three_param)
    # 陷阱行不放行 / 跨组组合不出现（配对正确性）
    assert "trap-cross" not in _ids(result)
    assert "trap-res" not in _ids(result)
    assert "trap-kb" not in _ids(result)


# ─────────────────────────────────────────────────────────────────────────────
# 空守卫（不变项）
# ─────────────────────────────────────────────────────────────────────────────


async def test_guard_empty_kb_resource_ids_no_call() -> None:
    """kb_resource_ids 空 → 提前 return []，不发起任何调用（现状防御保留）。"""
    platform = _SqlLikePlatform(
        [_row("t1", kb_id="k1", resource="r1", path="/a/p1.md")]
    )
    result = await resolve_document_objects_by_file_paths(
        platform=platform,  # type: ignore[arg-type]
        base_id="base-1",
        kb_resource_ids=(),
        file_paths_by_kb_id={"k1": ("/a/p1.md",)},
    )
    assert result == []
    assert platform.calls == []


async def test_guard_empty_groups_no_call() -> None:
    """无有效分组（空映射 / 全空 path）→ 提前 return []，不发起调用。"""
    platform = _SqlLikePlatform([])
    for groups in ({}, {"k1": ()}, {"k1": ("", None)}):
        result = await resolve_document_objects_by_file_paths(
            platform=platform,  # type: ignore[arg-type]
            base_id="base-1",
            kb_resource_ids=("r1",),
            file_paths_by_kb_id=groups,
        )
        assert result == []
    assert platform.calls == []

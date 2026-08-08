"""B 点 resolve_document_objects_by_file_paths 合并验收。

覆盖：
  端到端：单 kb 组 1 path，DB 匹配 >1000 行且前 1000 行 kb_id 不匹配 →
            现状（per-kb for 循环 + 过滤前 LIMIT）返回空 → 合并后返回非空。
  top_k 放大：N=3 → top_k=3000；N=15 → top_k=10000 + warning；恰好调用 1 次（循环合并）。
  等价性：2~3 个 kb 组、每组 2~3 个 path，含跨组命中 / kb_id 匹配但 path 不属该组 /
      kb_resource_id 不在白名单的行 → 合并输出 == 现状 for 循环输出（集合等价）；
      (kb_id, path) 跨组组合不出现。
  空守卫：kb_resource_ids 空 / 无有效路径 → 提前 return []，不发起调用。

基建：_SqlLikePlatform 模拟底层 SQL 下推语义（生效维度全 AND + LIMIT 截断在过滤后）；
_legacy_resolve 模拟现状 per-kb for 循环（label OR 通道 + LIMIT 1000 + 内存过滤）。
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


class _SqlLikePlatform:
    """模拟底层 SQL 下推语义：生效维度全 AND + LIMIT 截断（过滤后）。

    仅实现 search_terms_by_labels 一个方法；记录每次调用参数。
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
    """现状 per-kb for 循环等价实现（改造前 B 点逻辑）。

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
            if str((row.get("term_tags") or {}).get("kb_file_path") or "") in allowed_paths
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


# ─────────────────────────────────────────────────────────────────────────────
# top_k 放大规则 + 单次调用
# ─────────────────────────────────────────────────────────────────────────────


async def test_t6_three_groups_top_k_3000_single_call() -> None:
    """N=3 组 → top_k=min(1000*3,10000)=3000，且恰好调用 1 次。"""
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
    assert kwargs["kb_ids"] == ["k0", "k1", "k2"]
    assert kwargs["kb_file_paths"] == ["/kb0/p.md", "/kb1/p.md", "/kb2/p.md"]
    assert kwargs["kb_resource_ids"] == ["r1"]
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
    file_paths_by_kb_id = {
        f"k{i}": (f"/kb{i}/p.md",) for i in range(15)
    }
    with caplog.at_level(logging.WARNING, logger="datacloud_platform.mixins.document"):
        await resolve_document_objects_by_file_paths(
            platform=platform,  # type: ignore[arg-type]
            base_id="base-1",
            kb_resource_ids=("r1",),
            file_paths_by_kb_id=file_paths_by_kb_id,
        )
    assert len(platform.calls) == 1
    assert platform.calls[0][1]["top_k"] == 10000
    assert any("钳制" in rec.message or "cap" in rec.message.lower() for rec in caplog.records)


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
        _row(f"h{i}", kb_id="k1", resource="r1", path="/a/p1.md")
        for i in range(500)
    ]
    platform = _SqlLikePlatform(rows)
    file_paths_by_kb_id = {"k1": ("/a/p1.md",)}
    legacy = _legacy_resolve(rows, ("r1",), file_paths_by_kb_id)
    assert legacy == []  # 现状：LIMIT 内 1000 行全被内存滤掉

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
# 等价性：合并输出 == 现状 for 循环输出（集合等价 + 配对正确性）
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


async def test_t7_merged_equals_legacy_set(
    equiv_rows: list[dict[str, Any]],
) -> None:
    """合并输出与现状 for 循环输出集合等价；(kb_id, path) 跨组组合不出现。"""
    file_paths_by_kb_id = {
        "k1": ("/a/p1.md", "/a/p2.md"),
        "k2": ("/b/p1.md",),
    }
    kb_resource_ids = ("r1", "r2")

    legacy = _legacy_resolve(equiv_rows, kb_resource_ids, file_paths_by_kb_id)
    assert _ids(legacy) == {"r1a", "r1b", "r2a", "r2b"}

    platform = _SqlLikePlatform(equiv_rows)
    result = await resolve_document_objects_by_file_paths(
        platform=platform,  # type: ignore[arg-type]
        base_id="base-1",
        kb_resource_ids=kb_resource_ids,
        file_paths_by_kb_id=file_paths_by_kb_id,
    )
    assert _ids(result) == _ids(legacy)  # 集合等价
    assert len(result) == len(legacy)
    # 跨组组合不出现（配对正确性）
    assert "trap-cross" not in _ids(result)
    assert "trap-res" not in _ids(result)
    assert "trap-kb" not in _ids(result)


# ─────────────────────────────────────────────────────────────────────────────
# 空守卫
# ─────────────────────────────────────────────────────────────────────────────


async def test_guard_empty_kb_resource_ids_no_call() -> None:
    """kb_resource_ids 空 → 提前 return []，不发起任何调用（现状防御保留）。"""
    platform = _SqlLikePlatform([_row("t1", kb_id="k1", resource="r1", path="/a/p1.md")])
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

"""UC-01/UC-02/UC-03 前置：本体知识 BM25 检索 Tool 单元测试。"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.fixture()
def owl_docs_dir(tmp_path: Path) -> Path:
    """在临时目录写入两个 MD 文件，模拟 owl_docs/。"""
    customer_md = textwrap.dedent("""\
        # 客户（by_customer）

        **类型**：object
        **描述**：CRM 客户主数据，记录企业客户基本信息。

        ## 查询能力（query）

        按条件查询对象客户的明细记录。

        | 字段编码 | 中文名 | 角色 | 类型 |
        | --- | --- | --- | --- |
        | customer_name | 客户名称 | dimension | name |
        | industry | 行业 | dimension | name |
    """)
    view_md = textwrap.dedent("""\
        # 销售分析视图（scene_sales）

        **类型**：view
        **描述**：销售分析跨对象视图，聚合销售分析数据。

        ## 统计能力（compute）

        按规则对视图销售分析视图做分组统计。销售分析支持按行业、区域分组。
    """)
    (tmp_path / "by_customer.md").write_text(customer_md, encoding="utf-8")
    (tmp_path / "scene_sales.md").write_text(view_md, encoding="utf-8")
    return tmp_path


class TestOntologySearchTool:
    def test_search_returns_object_by_keyword(self, owl_docs_dir: Path) -> None:
        """关键词"客户"应命中 by_customer（object）。"""
        from tools.ontology_search_tool import build_ontology_search_tool

        tool = build_ontology_search_tool(owl_docs_dir)
        result: str = tool.invoke({"query": "客户"})

        assert "by_customer" in result
        assert "object" in result

    def test_search_returns_view_by_keyword(self, owl_docs_dir: Path) -> None:
        """关键词"销售分析"应命中 scene_sales（view）。"""
        from tools.ontology_search_tool import build_ontology_search_tool

        tool = build_ontology_search_tool(owl_docs_dir)
        result: str = tool.invoke({"query": "销售分析"})

        assert "scene_sales" in result
        assert "view" in result

    def test_search_no_match_returns_hint(self, owl_docs_dir: Path) -> None:
        """完全不相关的词应返回提示而非空字符串。"""
        from tools.ontology_search_tool import build_ontology_search_tool

        tool = build_ontology_search_tool(owl_docs_dir)
        result: str = tool.invoke({"query": "zzzznotexist"})

        assert "未找到" in result

    def test_search_top_k_limits_results(self, owl_docs_dir: Path) -> None:
        """top_k=1 时最多返回 1 条结果（分隔符 --- 最多出现 0 次）。"""
        from tools.ontology_search_tool import build_ontology_search_tool

        tool = build_ontology_search_tool(owl_docs_dir)
        result: str = tool.invoke({"query": "客户 销售", "top_k": 1})

        assert result.count("---") <= 1

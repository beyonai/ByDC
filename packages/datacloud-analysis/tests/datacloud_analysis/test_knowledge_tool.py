"""search_knowledge 工具单元测试

注意：在 tests/datacloud_analysis 下，pytest 可能将 tests 置于 path 首位，
导致 datacloud_analysis 解析为测试包。若导入失败则跳过。
"""

from unittest.mock import patch

import pytest

pytest.importorskip("datacloud_analysis.tools.knowledge")

import datacloud_analysis.tools.knowledge as knowledge_module
from datacloud_analysis.tools.knowledge import search_knowledge


async def _fake_to_thread(f, *a, **k):
    """同步执行 f，返回 awaitable"""
    return f(*a, **k)


@pytest.mark.asyncio
async def test_search_knowledge_unconfigured():
    """未配置 GRAPH_FILES 时返回空列表"""
    with patch.object(knowledge_module, "_get_knowledge_service", return_value=None):
        result = await search_knowledge.ainvoke({"query": "test", "top_k": 5})
        assert result == []


@pytest.mark.asyncio
async def test_search_knowledge_returns_snippets_format():
    """有结果时返回正确的 {title, content, source} 格式"""
    mock_result = {
        "entities_found": [{"name": "王小明"}],
        "results": [
            {
                "center_entity": {"name": "王小明"},
                "tree": {
                    "name": "王小明",
                    "node_type": "Term",
                    "properties": {},
                    "children": [],
                },
            }
        ],
    }
    mock_svc = type("MockSvc", (), {"query": lambda self, q, n: mock_result})()
    with patch.object(knowledge_module, "_get_knowledge_service", return_value=mock_svc):
        with patch("asyncio.to_thread", side_effect=_fake_to_thread):
            result = await search_knowledge.ainvoke({"query": "王小明", "top_k": 5})
            assert len(result) == 1
            assert result[0]["title"] == "王小明 相关子图"
            assert "source" in result[0] and result[0]["source"] == "knowledge_graph"
            assert "content" in result[0]

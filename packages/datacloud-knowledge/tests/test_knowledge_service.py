"""测试知识图谱查询服务"""

import sys
import os

# 将项目根目录加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest

pytest.importorskip("networkx")
pytest.importorskip("numpy")
pytest.importorskip("matplotlib")
pytest.importorskip("pypinyin")

from datacloud_knowledge_service import KnowledgeGraphQuery


def test_knowledge_graph_query():
    """测试知识图谱查询服务"""
    print("=" * 60)
    print("测试知识图谱查询服务")
    print("=" * 60)

    # 创建服务实例（不加载实际图文件，使用空图）
    service = KnowledgeGraphQuery(
        graph_files=None,  # 不加载图文件
        default_hops=4
    )

    print(f"✓ 服务创建成功")
    print(f"  - 默认跳数: {service.default_hops}")
    print(f"  - 图节点数: {len(service.graph.graph.nodes())}")
    print()

    # 测试导出空图
    graph_data = service.export_graph()
    print(f"✓ 图导出成功")
    print(f"  - 节点数: {len(graph_data.get('nodes', []))}")
    print(f"  - 边数: {len(graph_data.get('edges', []))}")
    print()

    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_knowledge_graph_query()

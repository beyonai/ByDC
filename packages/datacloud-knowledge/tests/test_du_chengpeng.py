#!/usr/bin/env python3
"""测试知识图谱查询 - 验证"杜成鹏跟进的商机"查询"""

import sys
import os

# 将项目根目录加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datacloud_knowledge import KnowledgeGraphQuery, TreeNode


def dict_to_tree(tree_dict: dict) -> TreeNode:
    """将字典转换为TreeNode"""
    node = TreeNode(
        id=tree_dict.get('id', ''),
        name=tree_dict.get('name', ''),
        node_type=tree_dict.get('node_type', ''),
        properties=tree_dict.get('properties', {}),
        relation=tree_dict.get('relation', '')
    )
    
    for child_dict in tree_dict.get('children', []):
        node.children.append(dict_to_tree(child_dict))
    
    return node


def print_tree(node: TreeNode, prefix: str = "", is_last: bool = True) -> str:
    """打印树形结构"""
    lines = []
    
    # 当前节点标识
    connector = "└── " if is_last else "├── "
    
    # 节点信息
    relation_str = f"[{node.relation}] -> " if node.relation else ""
    lines.append(f"{prefix}{connector}{relation_str}{node.name} [{node.node_type}]")
    
    # 准备下一层前缀
    new_prefix = prefix + ("    " if is_last else "│   ")
    
    # 打印属性
    if node.properties:
        lines.append(f"{new_prefix}├── 属性:")
        prop_prefix = new_prefix + "│   "
        props = list(node.properties.items())
        for i, (key, value) in enumerate(props):
            is_last_prop = (i == len(props) - 1) and not node.children
            prop_connector = "└── " if is_last_prop else "├── "
            # 截断过长的值
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:97] + "..."
            lines.append(f"{prop_prefix}{prop_connector}{key}: {value_str}")
    
    # 打印子节点
    for i, child in enumerate(node.children):
        is_last_child = (i == len(node.children) - 1)
        lines.append(print_tree(child, new_prefix, is_last_child))
    
    return "\n".join(lines)


def test_query_du_chengpeng():
    """测试查询杜成鹏跟进的商机"""
    print("=" * 70)
    print("测试: 杜成鹏跟进的商机")
    print("=" * 70)
    
    # 获取数据文件路径
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    graph_files = [
        os.path.join(data_dir, 'terms', 'base.json'),
        os.path.join(data_dir, 'terms', 'crm.json'),
        os.path.join(data_dir, 'scenes', 'main.json'),
    ]
    
    # 检查文件是否存在
    print("\n检查数据文件:")
    for f in graph_files:
        exists = os.path.exists(f)
        print(f"  {'✓' if exists else '✗'} {os.path.basename(f)}")
    
    # 创建服务实例
    print("\n初始化 KnowledgeGraphQuery...")
    service = KnowledgeGraphQuery(
        graph_files=graph_files,
        default_hops=4
    )
    print(f"✓ 服务初始化成功")
    print(f"  - 图节点数: {len(service.graph.graph.nodes())}")
    print(f"  - 图边数: {len(service.graph.graph.edges())}")
    
    # 执行查询
    print("\n" + "=" * 70)
    print("执行查询: '杜成鹏跟进的商机'")
    print("=" * 70)
    
    result = service.query("杜成鹏跟进的商机")
    
    # 打印识别的实体
    print(f"\n识别到的中心实体: {len(result.get('entities_found', []))} 个")
    print("(按匹配优先级排序: 精确匹配 > 别名匹配)")
    for i, entity in enumerate(result.get('entities_found', []), 1):
        match_type_str = "精确匹配" if entity.get('match_type') == 'standard_name' else "别名匹配"
        print(f"  {i}. {entity['name']} ({entity['node_type']}) - {match_type_str}")
    
    # 打印树形子图结果
    print("\n" + "=" * 70)
    print("树形子图结果:")
    print("=" * 70)
    
    results = result.get('results', [])
    if results:
        for i, subgraph in enumerate(results, 1):
            center_entity = subgraph.get('center_entity', {})
            print(f"\n【中心实体 {i}】{center_entity.get('name')}")
            print(f"节点数: {subgraph.get('node_count')}, 边数: {subgraph.get('edge_count')}")
            print(f"\n树形结构:")
            
            tree_dict = subgraph.get('tree')
            if tree_dict:
                tree = dict_to_tree(tree_dict)
                print(print_tree(tree, prefix="", is_last=True))
            else:
                print("  (无树形结构)")
    else:
        print("\n✗ 未返回子图结果")
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)
    
    return len(result.get('entities_found', [])) > 0


if __name__ == "__main__":
    success = test_query_du_chengpeng()
    sys.exit(0 if success else 1)

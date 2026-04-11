#!/usr/bin/env python3
"""测试知识图谱查询 - 验证"王小明他优秀吗"查询（SQL-native 实现）"""

import sys
from importlib import import_module
from pathlib import Path
from typing import Any

# 将项目 src 目录加入路径
PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

_KG_MODULE = import_module("datacloud_knowledge")
SQLKnowledgeGraphQuery = _KG_MODULE.SQLKnowledgeGraphQuery
TreeNode = _KG_MODULE.TreeNode


def dict_to_tree(tree_dict: dict[str, Any]) -> TreeNode:
    """将字典转换为TreeNode"""
    node = TreeNode(
        id=tree_dict.get("id", ""),
        name=tree_dict.get("name", ""),
        node_type=tree_dict.get("node_type", ""),
        properties=tree_dict.get("properties", {}),
        relation=tree_dict.get("relation", ""),
    )

    for child_dict in tree_dict.get("children", []):
        node.children.append(dict_to_tree(child_dict))

    return node


def print_tree(node: TreeNode, prefix: str = "", is_last: bool = True) -> str:
    """打印树形结构"""
    lines = []

    connector = "└── " if is_last else "├── "
    relation_str = f"[{node.relation}] -> " if node.relation else ""
    lines.append(f"{prefix}{connector}{relation_str}{node.name} [{node.node_type}]")

    new_prefix = prefix + ("    " if is_last else "│   ")

    if node.properties:
        lines.append(f"{new_prefix}├── 属性:")
        prop_prefix = new_prefix + "│   "
        props = list(node.properties.items())
        for i, (key, value) in enumerate(props):
            is_last_prop = (i == len(props) - 1) and not node.children
            prop_connector = "└── " if is_last_prop else "├── "
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:97] + "..."
            lines.append(f"{prop_prefix}{prop_connector}{key}: {value_str}")

    for i, child in enumerate(node.children):
        is_last_child = i == len(node.children) - 1
        lines.append(print_tree(child, new_prefix, is_last_child))

    return "\n".join(lines)


def test_wang_xiaoming() -> None:
    """测试查询王小明他优秀吗（SQL-native 实现）"""
    print("=" * 70)
    print("测试: 王小明他优秀吗")
    print("=" * 70)

    # 从真实 .env 加载环境变量
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)

    # 创建 SQL-native 服务实例
    print("\n初始化 SQLKnowledgeGraphQuery...")
    service = SQLKnowledgeGraphQuery(default_hops=4)
    print("✓ 服务初始化成功（使用 PostgreSQL 递归 CTE）")

    # 执行查询
    print("\n" + "=" * 70)
    print("执行查询: '王小明他优秀吗'")
    print("=" * 70)

    result = service.query("王小明他优秀吗")

    # 打印识别的实体
    print(f"\n识别到的中心实体: {len(result.get('entities_found', []))} 个")
    print("(按匹配优先级排序: 精确匹配 > 别名匹配)")
    for i, entity in enumerate(result.get("entities_found", []), 1):
        match_type_str = "精确匹配" if entity.get("match_type") == "standard_name" else "别名匹配"
        print(f"  {i}. {entity['name']} ({entity['node_type']}) - {match_type_str}")

    # 打印树形子图结果
    print("\n" + "=" * 70)
    print("树形子图结果:")
    print("=" * 70)

    results = result.get("results", [])
    if results:
        for i, subgraph in enumerate(results, 1):
            center_entity = subgraph.get("center_entity", {})
            print(f"\n【中心实体 {i}】{center_entity.get('name')}")
            print(f"节点数: {subgraph.get('node_count')}, 边数: {subgraph.get('edge_count')}")
            print("\n树形结构:")

            tree_dict = subgraph.get("tree")
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

    assert len(result.get("entities_found", [])) > 0, (
        "未识别到任何实体，请确认 PG 中已导入相关术语数据"
    )


if __name__ == "__main__":
    try:
        test_wang_xiaoming()
        sys.exit(0)
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        sys.exit(1)

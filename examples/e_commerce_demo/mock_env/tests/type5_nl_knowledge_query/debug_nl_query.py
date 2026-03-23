from pathlib import Path

from datacloud_knowledge import SQLKnowledgeGraphQuery, TreeNode


def dict_to_tree(tree_dict: dict) -> TreeNode:
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


def execute_nl_query(query_text: str, service: SQLKnowledgeGraphQuery | None = None) -> dict:
    """执行自然语言查询并返回结果"""
    if service is None:
        service = SQLKnowledgeGraphQuery(default_hops=4)

    print(f"\n执行查询: '{query_text}'")
    result = service.query(query_text)

    # 打印识别的实体
    entities = result.get("entities_found", [])
    print(f"识别到的中心实体: {len(entities)} 个")
    for i, entity in enumerate(entities, 1):
        match_type_str = "精确匹配" if entity.get("match_type") == "standard_name" else "别名匹配"
        print(f"  {i}. {entity['name']} ({entity['node_type']}) - {match_type_str}")

    return result


def print_query_results(result: dict, query_name: str) -> None:
    """打印查询结果"""
    print(f"\n{'=' * 70}")
    print(f"【{query_name}】查询结果")
    print(f"{'=' * 70}")

    results = result.get("results", [])
    if results:
        for i, subgraph in enumerate(results, 1):
            center_entity = subgraph.get("center_entity", {})
            print(f"\n【中心实体 {i}】{center_entity.get('name')}")
            print(f"节点数: {subgraph.get('node_count')}, 边数: {subgraph.get('edge_count')}")

            tree_dict = subgraph.get("tree")
            if tree_dict:
                tree = dict_to_tree(tree_dict)
                print(f"\n树形结构:")
                print(print_tree(tree, prefix="", is_last=True))
            else:
                print("  (无树形结构)")
    else:
        print("\n✗ 未返回子图结果")

def main():
    query = '帮我看一下"北京亦庄经济技术开发区"区域内单位亩产效益最低的10家企业'

    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[2] / ".env.example"
    if env_path.exists():
        load_dotenv(env_path, override=True)
    service = SQLKnowledgeGraphQuery(default_hops=2)

    result = execute_nl_query(query, service)
    print_query_results(result, "亩产效益最低的10家企业")

if __name__ == '__main__':
    main()
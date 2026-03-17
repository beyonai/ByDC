"""
自然语言查询N跳子图 - 树形展示版本

功能：输入自然语言，解析所有匹配实体作为中心节点，以树形结构展示N跳子图
示例："王小明他优秀吗" -> 查询"王小明"的2跳子图，树形展示关系和属性
"""

import json
import re
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from ..graph.model import MetadataGraph, NodeLabel, EdgeLabel
from ..graph.tokenizer import FullTokenizer, TermDictionary


@dataclass
class QueryEntity:
    """查询识别的实体"""
    name: str  # 实体名称
    node_id: Optional[str] = None  # 图中节点ID
    node_type: Optional[str] = None  # 节点类型
    match_score: float = 0.0  # 匹配分数
    match_type: str = ""  # 匹配类型: exact, alias, pinyin, index_match
    matched_text: str = ""  # 在查询中匹配到的文本


@dataclass
class TreeNode:
    """树形节点"""
    id: str
    name: str
    node_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    children: List['TreeNode'] = field(default_factory=list)
    relation: str = ""  # 与父节点的关系
    level: int = 0


@dataclass
class SubgraphResult:
    """子图查询结果"""
    center_entity: QueryEntity
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    hops: int = 0
    tree: Optional[TreeNode] = None  # 树形结构


class NaturalLanguageGraphQuery:
    """自然语言图查询器 - 树形展示版"""
    
    def __init__(self, graph: MetadataGraph, tokenizer: Optional[FullTokenizer] = None):
        self.graph = graph
        self.tokenizer = tokenizer
        self._build_name_index()
    
    def _build_name_index(self):
        """构建名称索引，用于快速查找实体"""
        self.name_to_nodes: Dict[str, List[Tuple[str, str, str]]] = {}
        # name -> [(node_id, node_type, match_type), ...]
        # match_type: "standard_name" or "alias"
        
        for node_id, data in self.graph.graph.nodes(data=True):
            node_type = data.get("node_type")
            
            if node_type == NodeLabel.TERM.value:
                # Term节点：索引 standard_name 和 aliases
                standard_name = data.get("standard_name", "")
                if standard_name:
                    if standard_name not in self.name_to_nodes:
                        self.name_to_nodes[standard_name] = []
                    self.name_to_nodes[standard_name].append((node_id, node_type, "standard_name"))
                
                # 索引别名
                properties = data.get("properties", {})
                aliases = properties.get("aliases", [])
                for alias in aliases:
                    if alias and alias != standard_name:
                        if alias not in self.name_to_nodes:
                            self.name_to_nodes[alias] = []
                        self.name_to_nodes[alias].append((node_id, node_type, "alias"))
            
            elif node_type == NodeLabel.TERM_TYPE.value:
                # TermType节点：索引 name 和 code
                name = data.get("name", "")
                code = data.get("code", "")
                if name:
                    if name not in self.name_to_nodes:
                        self.name_to_nodes[name] = []
                    self.name_to_nodes[name].append((node_id, node_type, "standard_name"))
                if code and code != name:
                    if code not in self.name_to_nodes:
                        self.name_to_nodes[code] = []
                    self.name_to_nodes[code].append((node_id, node_type, "alias"))
            
            elif node_type == NodeLabel.FIELD.value:
                # Field节点：索引 name
                name = data.get("name", "")
                if name:
                    if name not in self.name_to_nodes:
                        self.name_to_nodes[name] = []
                    self.name_to_nodes[name].append((node_id, node_type, "standard_name"))
    
    def extract_entities(self, query: str) -> List[QueryEntity]:
        """
        从自然语言查询中提取所有匹配的实体
        
        策略：
        1. 找到所有匹配的实体（精确匹配、别名匹配）
        2. 按匹配类型排序：精确匹配 > 别名匹配
        3. 同一匹配类型内按匹配文本长度降序
        """
        entities = []
        matched_positions = set()
        
        # 按名称长度降序排序，优先匹配长名称
        sorted_names = sorted(self.name_to_nodes.keys(), key=len, reverse=True)
        
        for name in sorted_names:
            # 查找所有匹配位置
            pattern = re.escape(name)
            for match in re.finditer(pattern, query):
                start, end = match.span()
                
                # 检查是否与已匹配区域重叠
                if any(pos in matched_positions for pos in range(start, end)):
                    continue
                
                # 标记为已匹配
                for pos in range(start, end):
                    matched_positions.add(pos)
                
                # 添加所有匹配的实体
                for node_id, node_type, match_type in self.name_to_nodes[name]:
                    # 计算匹配分数：精确匹配1.0，别名0.9
                    score = 1.0 if match_type == "standard_name" else 0.9
                    
                    entity = QueryEntity(
                        name=name,
                        node_id=node_id,
                        node_type=node_type,
                        match_score=score,
                        match_type=match_type,
                        matched_text=name
                    )
                    entities.append(entity)
        
        # 去重：按 node_id 去重，但保留匹配类型信息
        seen_ids = {}
        unique_entities = []
        for entity in entities:
            if entity.node_id not in seen_ids:
                seen_ids[entity.node_id] = entity
                unique_entities.append(entity)
            else:
                # 如果已存在，保留分数更高的
                existing = seen_ids[entity.node_id]
                if entity.match_score > existing.match_score:
                    seen_ids[entity.node_id] = entity
                    unique_entities.remove(existing)
                    unique_entities.append(entity)
        
        # 排序：精确匹配优先，然后按匹配文本长度降序
        unique_entities.sort(key=lambda e: (-e.match_score, -len(e.matched_text)))
        
        return unique_entities
    
    def query_n_hop_subgraph(
        self,
        entity: QueryEntity,
        n_hops: int = 2,
        include_incoming: bool = True,
        include_outgoing: bool = True
    ) -> SubgraphResult:
        """
        查询N跳子图，构建树形结构
        """
        if not entity.node_id:
            return SubgraphResult(center_entity=entity, hops=n_hops)
        
        # BFS遍历N跳
        visited_nodes: Dict[str, Dict] = {entity.node_id: dict(self.graph.graph.nodes[entity.node_id])}
        visited_edges: Set[Tuple[str, str, str]] = set()
        current_level: Dict[str, int] = {entity.node_id: 0}  # node_id -> level
        
        for hop in range(n_hops):
            next_level: Dict[str, int] = {}
            
            for node_id, current_hop in current_level.items():
                # 出边
                if include_outgoing:
                    for target, edge_data_dict in self.graph.graph[node_id].items():
                        try:
                            for key, data in edge_data_dict.items():
                                edge_key = str(key) if key else ""
                                if (node_id, target, edge_key) not in visited_edges:
                                    visited_edges.add((node_id, target, edge_key))
                                    if target not in visited_nodes:
                                        visited_nodes[target] = dict(self.graph.graph.nodes[target])
                                        next_level[target] = current_hop + 1
                        except (AttributeError, TypeError):
                            pass
                
                # 入边
                if include_incoming:
                    for source in self.graph.graph.predecessors(node_id):
                        edge_data_dict = self.graph.graph[source][node_id]
                        try:
                            for key, data in edge_data_dict.items():
                                edge_key = str(key) if key else ""
                                if (source, node_id, edge_key) not in visited_edges:
                                    visited_edges.add((source, node_id, edge_key))
                                    if source not in visited_nodes:
                                        visited_nodes[source] = dict(self.graph.graph.nodes[source])
                                        next_level[source] = current_hop + 1
                        except (AttributeError, TypeError):
                            pass
            
            current_level = next_level
            if not current_level:
                break
        
        # 构建结果
        result = SubgraphResult(center_entity=entity, hops=n_hops)
        
        # 收集节点信息
        for node_id, node_data in visited_nodes.items():
            node_data = dict(node_data)
            node_data["_id"] = node_id
            result.nodes.append(node_data)
        
        # 收集边信息
        edge_relations = {}  # (source, target) -> relation
        for source, target, key in visited_edges:
            try:
                if key and key != "":
                    edge_data = self.graph.graph[source][target][key]
                else:
                    edge_data_dict = self.graph.graph[source][target]
                    first_key = list(edge_data_dict.keys())[0]
                    edge_data = edge_data_dict[first_key]
            except (KeyError, IndexError):
                edge_data = {}
            
            relation = "RELATED_TO"
            if isinstance(edge_data, dict):
                relation = edge_data.get("relation", "RELATED_TO")
            
            edge_info = {
                "source": source,
                "target": target,
                "relation": relation,
                "data": edge_data if isinstance(edge_data, dict) else {}
            }
            result.edges.append(edge_info)
            edge_relations[(source, target)] = relation
        
        # 构建树形结构
        result.tree = self._build_tree(entity.node_id, visited_nodes, edge_relations, n_hops)
        
        return result
    
    def _build_tree(
        self,
        root_id: str,
        nodes: Dict[str, Dict],
        edge_relations: Dict[Tuple[str, str], str],
        max_depth: int
    ) -> TreeNode:
        """构建树形结构"""
        root_data = nodes[root_id]
        
        # 创建根节点
        root = TreeNode(
            id=root_id,
            name=self._get_node_name(root_id, root_data),
            node_type=root_data.get("node_type", "Unknown"),
            properties=self._get_node_properties(root_data),
            level=0
        )
        
        # BFS构建树
        visited = {root_id}
        queue = [(root_id, root, 0)]
        
        while queue:
            current_id, current_node, current_level = queue.pop(0)
            
            if current_level >= max_depth:
                continue
            
            # 查找所有出边
            for (source, target), relation in edge_relations.items():
                if source == current_id and target not in visited:
                    visited.add(target)
                    target_data = nodes.get(target, {})
                    
                    child = TreeNode(
                        id=target,
                        name=self._get_node_name(target, target_data),
                        node_type=target_data.get("node_type", "Unknown"),
                        properties=self._get_node_properties(target_data),
                        relation=relation,
                        level=current_level + 1
                    )
                    
                    current_node.children.append(child)
                    queue.append((target, child, current_level + 1))
            
            # 查找所有入边（反向关系）
            for (source, target), relation in edge_relations.items():
                if target == current_id and source not in visited:
                    visited.add(source)
                    source_data = nodes.get(source, {})
                    
                    child = TreeNode(
                        id=source,
                        name=self._get_node_name(source, source_data),
                        node_type=source_data.get("node_type", "Unknown"),
                        properties=self._get_node_properties(source_data),
                        relation=f"<-{relation}",  # 标记为反向关系
                        level=current_level + 1
                    )
                    
                    current_node.children.append(child)
                    queue.append((source, child, current_level + 1))
        
        return root
    
    def _get_node_name(self, node_id: str, node_data: Dict) -> str:
        """获取节点显示名称"""
        node_type = node_data.get("node_type", "")
        
        if node_type == NodeLabel.TERM.value:
            return node_data.get("standard_name", node_id)
        elif node_type == NodeLabel.TERM_TYPE.value:
            return f"{node_data.get('name', '')}({node_data.get('code', '')})"
        elif node_type == NodeLabel.FIELD.value:
            return f"{node_data.get('object_id', '')}.{node_data.get('name', '')}"
        else:
            return node_data.get("name", node_id)
    
    def _get_node_properties(self, node_data: Dict) -> Dict[str, Any]:
        """获取节点属性 - 只从properties中提取，过滤拼音和别名"""
        properties = {}
        
        # 只从 properties 中提取，过滤掉拼音和别名
        props = node_data.get("properties", {})
        if isinstance(props, dict):
            for key, value in props.items():
                # 过滤掉拼音和别名
                if key not in ["aliases", "pinyin"]:
                    properties[key] = value
        
        return properties
    
    def query(
        self,
        natural_language: str,
        n_hops: int = 2,
        include_incoming: bool = True,
        include_outgoing: bool = True
    ) -> Dict[str, Any]:
        """主查询接口"""
        # 1. 提取所有实体
        entities = self.extract_entities(natural_language)
        
        if not entities:
            return {
                "query": natural_language,
                "entities_found": [],
                "results": [],
                "message": "未找到匹配的实体"
            }
        
        # 2. 对每个实体查询N跳子图
        results = []
        for entity in entities:
            subgraph = self.query_n_hop_subgraph(
                entity,
                n_hops=n_hops,
                include_incoming=include_incoming,
                include_outgoing=include_outgoing
            )
            results.append(self._format_subgraph_result(subgraph))
        
        return {
            "query": natural_language,
            "entities_found": [
                {
                    "name": e.name,
                    "node_id": e.node_id,
                    "node_type": e.node_type,
                    "match_type": e.match_type,
                    "match_score": e.match_score
                }
                for e in entities
            ],
            "n_hops": n_hops,
            "results": results
        }
    
    def _format_subgraph_result(self, subgraph: SubgraphResult) -> Dict[str, Any]:
        """格式化子图结果"""
        return {
            "center_entity": {
                "name": subgraph.center_entity.name,
                "node_id": subgraph.center_entity.node_id,
                "node_type": subgraph.center_entity.node_type,
                "match_type": subgraph.center_entity.match_type
            },
            "hops": subgraph.hops,
            "node_count": len(subgraph.nodes),
            "edge_count": len(subgraph.edges),
            "tree": self._tree_to_dict(subgraph.tree) if subgraph.tree else None
        }
    
    def _tree_to_dict(self, tree: TreeNode) -> Dict[str, Any]:
        """将树转换为字典"""
        return {
            "id": tree.id,
            "name": tree.name,
            "node_type": tree.node_type,
            "properties": tree.properties,
            "relation": tree.relation,
            "level": tree.level,
            "children": [self._tree_to_dict(child) for child in tree.children]
        }


def load_graph_from_json(json_files: str) -> MetadataGraph:
    """
    从JSON文件加载图，支持多个文件合并
    
    Args:
        json_files: 单个文件路径或用逗号分隔的多个文件路径
                   例如: "term_graph.json" 或 "term_graph.json,scene_graph.json"
    
    Returns:
        合并后的 MetadataGraph
    """
    graph = MetadataGraph()
    
    # 解析文件列表
    file_list = [f.strip() for f in json_files.split(",")]
    
    total_nodes = 0
    total_edges = 0
    
    for json_file in file_list:
        print(f"加载图数据: {json_file}")
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 添加节点
            nodes_added = 0
            for node_data in data.get("nodes", []):
                node_id = node_data.get("id")
                if node_id and node_id not in graph.graph:
                    graph.graph.add_node(node_id, **node_data)
                    nodes_added += 1
            
            # 添加边
            edges_added = 0
            for edge_data in data.get("edges", []):
                source = edge_data.get("source")
                target = edge_data.get("target")
                key = edge_data.get("key", None)
                
                edge_attrs = {k: v for k, v in edge_data.items() 
                             if k not in ["source", "target", "key"]}
                
                # 检查边是否已存在
                edge_exists = False
                if source in graph.graph and target in graph.graph:
                    if graph.graph.has_edge(source, target):
                        # 检查是否已有相同的key
                        if key and key in graph.graph[source][target]:
                            edge_exists = True
                
                if not edge_exists:
                    if key:
                        graph.graph.add_edge(source, target, key=key, **edge_attrs)
                    else:
                        graph.graph.add_edge(source, target, **edge_attrs)
                    edges_added += 1
            
            total_nodes += nodes_added
            total_edges += edges_added
            print(f"  - 新增节点: {nodes_added}, 新增边: {edges_added}")
            
        except FileNotFoundError:
            print(f"  - 文件不存在，跳过: {json_file}")
        except Exception as e:
            print(f"  - 加载失败: {e}")
    
    print(f"图加载完成: {graph.graph.number_of_nodes()} 节点, {graph.graph.number_of_edges()} 边")
    print(f"  (从 {len(file_list)} 个文件加载，共新增 {total_nodes} 节点, {total_edges} 边)")
    
    return graph


def print_tree(node: TreeNode, prefix: str = "", is_last: bool = True) -> str:
    """
    打印树形结构
    
    示例：
    王小明 [Term]
    ├── 属性:
    │   ├── 标准名称: 王小明
    │   ├── 领域: tech
    │   └── 部门: 技术部
    ├── IS_MEMBER_OF -> 员工名称(staffName) [TermType]
    │   └── DEFINES_FIELD -> po_users.userName [Field]
    └── MANAGES -> 李红 [Term]
    """
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
            lines.append(f"{prop_prefix}{prop_connector}{key}: {value}")
    
    # 打印子节点
    for i, child in enumerate(node.children):
        is_last_child = (i == len(node.children) - 1)
        lines.append(print_tree(child, new_prefix, is_last_child))
    
    return "\n".join(lines)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='自然语言查询N跳子图（树形展示，支持多图合并）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 单图查询
  python natural_language_graph_query.py -g term_graph.json -q "王小明"
  
  # 多图合并查询（用逗号分隔）
  python natural_language_graph_query.py -g term_graph.json,scene_graph.json -q "王小明"
  
  # 指定跳数
  python natural_language_graph_query.py -g term_graph.json -q "王小明" -n 3
        """
    )
    parser.add_argument('--graph', '-g', default='term_graph.json',
                       help='图数据JSON文件路径，多个文件用逗号分隔（默认: term_graph.json）')
    parser.add_argument('--query', '-q', required=True,
                       help='自然语言查询')
    parser.add_argument('--hops', '-n', type=int, default=2,
                       help='跳数（默认2）')
    parser.add_argument('--output', '-o',
                       help='输出结果到JSON文件')
    
    args = parser.parse_args()
    
    # 加载图（支持多个文件）
    graph = load_graph_from_json(args.graph)
    
    # 初始化 tokenizer（使用第一个图文件）
    first_graph_file = args.graph.split(',')[0].strip()
    print(f"\n初始化分词器（基于: {first_graph_file}）...")
    tokenizer = FullTokenizer(first_graph_file)
    
    # 创建查询器
    query_engine = NaturalLanguageGraphQuery(graph, tokenizer=tokenizer)
    
    # 执行查询
    print(f"\n查询: '{args.query}'")
    print(f"跳数: {args.hops}")
    print("=" * 70)
    
    result = query_engine.query(args.query, n_hops=args.hops)
    
    # 打印结果
    print(f"\n识别到的中心实体: {len(result['entities_found'])} 个")
    print("(按匹配优先级排序: 精确匹配 > 别名匹配)")
    for i, entity in enumerate(result['entities_found'], 1):
        match_type_str = "精确匹配" if entity['match_type'] == 'standard_name' else "别名匹配"
        print(f"  {i}. {entity['name']} ({entity['node_type']}) - {match_type_str}")
    
    print(f"\n" + "=" * 70)
    print(f"树形子图结果:")
    print("=" * 70)
    
    for i, subgraph in enumerate(result['results'], 1):
        print(f"\n【中心实体 {i}】{subgraph['center_entity']['name']}")
        print(f"节点数: {subgraph['node_count']}, 边数: {subgraph['edge_count']}")
        print(f"\n树形结构:")
        
        if subgraph['tree']:
            # 重建TreeNode对象以便打印
            tree = dict_to_tree(subgraph['tree'])
            print(print_tree(tree, prefix="", is_last=True))
    
    # 保存结果
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {args.output}")
    
    return result


def dict_to_tree(tree_dict: Dict) -> TreeNode:
    """将字典转换为TreeNode"""
    node = TreeNode(
        id=tree_dict['id'],
        name=tree_dict['name'],
        node_type=tree_dict['type'],
        properties=tree_dict.get('properties', {}),
        relation=tree_dict.get('relation', ''),
        level=tree_dict.get('level', 0)
    )
    
    for child_dict in tree_dict.get('children', []):
        node.children.append(dict_to_tree(child_dict))
    
    return node


if __name__ == "__main__":
    main()

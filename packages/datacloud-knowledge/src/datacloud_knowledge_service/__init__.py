"""DataCloud Knowledge Service - 知识检索与查询计划生成服务.

提供功能：
- 根据问题检索知识（业务知识、本体知识）
- 生成并返回数据查询计划
- 术语自动发现与沉淀
- 自然语言查询图谱知识（默认4跳）

示例:
    >>> from datacloud_knowledge_service import KnowledgeGraphQuery
    >>> service = KnowledgeGraphQuery(graph_files=["term_graph.json", "scene_graph.json"])
    >>> result = service.query("杜成鹏跟进的商机")
    >>> print(result)
"""

__version__ = "0.1.0"

from typing import Any
from .graph import (
    MetadataGraph,
    TermNode,
    TermTypeNode,
    EdgeLabel,
    FullTokenizer,
)
from .query import (
    NaturalLanguageGraphQuery,
    QueryEntity,
    TreeNode,
    SubgraphResult,
)


class KnowledgeGraphQuery:
    """知识图谱查询服务主类.
    
    提供自然语言查询图谱知识的核心功能，默认查询4跳范围内的知识。
    
    Attributes:
        graph: MetadataGraph实例
        query_engine: NaturalLanguageGraphQuery实例
        default_hops: 默认查询跳数（默认为4）
    """
    
    def __init__(
        self,
        graph_files: list[str] | None = None,
        tokenizer: FullTokenizer | None = None,
        default_hops: int = 4,
    ):
        """初始化知识图谱查询服务.
        
        Args:
            graph_files: JSON图文件路径列表，默认加载全部
            tokenizer: 分词器实例，如果为None则自动创建
            default_hops: 默认查询跳数，默认为4
        """
        self.graph = MetadataGraph()
        self.default_hops = default_hops
        
        # 加载图文件
        if graph_files:
            for file_path in graph_files:
                self._import_json(file_path)
        
        # 初始化查询引擎
        self.query_engine = NaturalLanguageGraphQuery(
            graph=self.graph,
            tokenizer=tokenizer
        )
    
    def _import_json(self, filepath: str):
        """导入JSON文件到图中"""
        import json
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 导入节点
        for node_data in data.get('nodes', []):
            node_id = node_data.get('id')
            if node_id:
                self.graph.graph.add_node(node_id, **node_data)
        
        # 导入边
        for edge_data in data.get('edges', []):
            source = edge_data.get('source')
            target = edge_data.get('target')
            if source and target:
                self.graph.graph.add_edge(source, target, **edge_data)
    
    def query(
        self,
        question: str,
        n_hops: int | None = None,
    ) -> dict[str, Any]:
        """执行自然语言查询.
        
        Args:
            question: 自然语言问题
            n_hops: 查询跳数，默认为4
            
        Returns:
            查询结果字典
            
        Example:
            >>> service = KnowledgeGraphQuery(["term_graph.json"])
            >>> result = service.query("杜成鹏跟进的商机")
            >>> print(f"找到实体: {len(result['entities_found'])}")
        """
        hops = n_hops or self.default_hops
        return self.query_engine.query(
            natural_language=question,
            n_hops=hops
        )
    
    def query_entities(
        self,
        question: str,
        n_hops: int | None = None,
    ) -> list[QueryEntity]:
        """查询并返回匹配实体列表.
        
        Args:
            question: 自然语言问题
            n_hops: 查询跳数，默认为4
            
        Returns:
            QueryEntity列表
        """
        hops = n_hops or self.default_hops
        result = self.query_engine.query(
            natural_language=question,
            n_hops=hops
        )
        
        entities = []
        for entity_data in result.get('entities_found', []):
            entity = QueryEntity(
                name=entity_data.get('name', ''),
                node_id=entity_data.get('node_id'),
                node_type=entity_data.get('node_type'),
                match_score=entity_data.get('match_score', 0.0),
                match_type=entity_data.get('match_type', ''),
            )
            entities.append(entity)
        return entities
    
    def get_term_by_name(self, name: str) -> dict[str, Any] | None:
        """根据名称获取术语.
        
        Args:
            name: 术语名称
            
        Returns:
            术语数据字典，如果未找到则返回None
        """
        return self.graph.get_term_by_name(name)
    
    def export_graph(self) -> dict[str, Any]:
        """导出图为字典格式.
        
        Returns:
            图数据字典
        """
        return self.graph.export_to_json()


__all__ = [
    "__version__",
    # 主类
    "KnowledgeGraphQuery",
    # 图模型
    "MetadataGraph",
    "TermNode",
    "TermTypeNode",
    "EdgeLabel",
    "FullTokenizer",
    # 查询
    "NaturalLanguageGraphQuery",
    "QueryEntity",
    "TreeNode",
    "SubgraphResult",
]

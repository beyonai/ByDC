"""DataCloud Knowledge Service - 知识检索与查询计划生成服务.

提供功能：
- 根据问题检索知识（业务知识、本体知识）
- 生成并返回数据查询计划
- 术语自动发现与沉淀
- 自然语言查询图谱知识（默认4跳）

两种实现模式：
1. SQL-native: 使用 PostgreSQL 递归 CTE（推荐，无需加载全图到内存）
2. NetworkX: 内存中图计算（legacy，需要加载 JSON 文件）

示例 (SQL-native):
    >>> from datacloud_knowledge_service import SQLKnowledgeGraphQuery
    >>> service = SQLKnowledgeGraphQuery()  # 自动读取 DB 环境变量
    >>> result = service.query("杜成鹏跟进的商机")
    >>> print(result)

示例 (NetworkX legacy):
    >>> from datacloud_knowledge_service import KnowledgeGraphQuery
    >>> service = KnowledgeGraphQuery(graph_files=["term_graph.json"])
    >>> result = service.query("杜成鹏跟进的商机")
    >>> print(result)
"""

__version__ = "0.2.0"

from typing import Any

# NetworkX-based (legacy)
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

# SQL-native (new)
from .query.sql_engine import (
    SQLGraphQuery,
    SQLKnowledgeGraphQuery,
    create_sql_graph_query,
)


# Backward-compatible wrapper - delegates to SQLGraphQuery
class KnowledgeGraphQuery(SQLKnowledgeGraphQuery):
    """知识图谱查询服务主类 - 现在使用 SQL-native 实现.

    为了保持向后兼容，此类继承自 SQLKnowledgeGraphQuery。
    graph_files 参数已废弃（数据从 PostgreSQL 读取）。

    Attributes:
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
            graph_files: **已废弃** - 数据现在从 PostgreSQL 读取
            tokenizer: **已废弃** - 不再使用
            default_hops: 默认查询跳数，默认为4
        """
        import warnings

        if graph_files:
            warnings.warn(
                "graph_files 参数已废弃，数据现在从 PostgreSQL 读取。"
                "如需自定义 DB 配置，请使用 SQLKnowledgeGraphQuery(db_config=...)",
                DeprecationWarning,
                stacklevel=2,
            )

        if tokenizer:
            warnings.warn(
                "tokenizer 参数已废弃，实体匹配现在通过 SQL 查询 term 表完成",
                DeprecationWarning,
                stacklevel=2,
            )

        # Initialize SQL-native engine
        super().__init__(db_config=None, default_hops=default_hops)

    def get_term_by_name(self, name: str) -> dict[str, Any] | None:
        """根据名称获取术语.

        Args:
            name: 术语名称

        Returns:
            术语数据字典，如果未找到则返回None
        """
        # Query from DB via SQLGraphQuery
        entities = self.sql_engine.extract_entities(name)
        if entities:
            entity = entities[0]
            return {
                "id": entity.node_id,
                "name": entity.name,
                "node_type": entity.node_type,
            }
        return None

    def export_graph(self) -> dict[str, Any]:
        """导出图为字典格式.

        Returns:
            图数据字典（从数据库查询）
        """
        # Export from DB - query all terms and relations
        import os
        import psycopg2

        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5432")),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD", ""),
            dbname=os.environ.get("DB_NAME", "postgres"),
        )

        try:
            with conn.cursor() as cur:
                # Query all nodes (terms)
                cur.execute("""
                    SELECT term_id, term_name, term_type_code, term_tags
                    FROM whale_datacloud.term
                """)
                nodes = []
                for term_id, term_name, term_type, tags in cur.fetchall():
                    nodes.append(
                        {
                            "id": term_id,
                            "name": term_name,
                            "node_type": term_type,
                            "properties": tags or {},
                        }
                    )

                # Query all edges (relations)
                cur.execute("""
                    SELECT source_term_id, target_term_id, relation_name
                    FROM whale_datacloud.term_relation
                """)
                edges = []
                for source, target, relation in cur.fetchall():
                    edges.append({"source": source, "target": target, "relation": relation})

                return {"nodes": nodes, "edges": edges}
        finally:
            conn.close()


__all__ = [
    "__version__",
    # SQL-native (recommended)
    "SQLKnowledgeGraphQuery",
    "SQLGraphQuery",
    "create_sql_graph_query",
    # Legacy NetworkX-based
    "KnowledgeGraphQuery",
    "MetadataGraph",
    "TermNode",
    "TermTypeNode",
    "EdgeLabel",
    "FullTokenizer",
    "NaturalLanguageGraphQuery",
    # Common data classes
    "QueryEntity",
    "TreeNode",
    "SubgraphResult",
]

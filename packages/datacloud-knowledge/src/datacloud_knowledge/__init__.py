"""DataCloud Knowledge SDK.

该包位于 `packages/datacloud-knowledge/src/datacloud_knowledge/`。
"""

from typing import Any

from .file_store.manager import FileManager
from .file_store.settings import FileStoreSettings
from .graph import (
    DomainNode,
    EdgeLabel,
    FieldNode,
    FullTokenizer,
    MetadataGraph,
    NodeLabel,
    ObjectNode,
    Properties,
    TermDictionary,
    TermLibraryNode,
    TermNode,
    TermTypeNode,
)
from .query import (
    NaturalLanguageGraphQuery,
    QueryEntity,
    SubgraphResult,
    TreeNode,
)
from .query.sql_engine import (
    SQLGraphQuery,
    SQLKnowledgeGraphQuery,
    create_sql_graph_query,
    nl_to_semantic_tree,
    get_singleton_service,
    reset_singleton_service,
)
from .query.vocab_cache import (
    VocabularyCache,
    DEFAULT_CACHE_DIR,
    CACHE_DIR_ENV,
)

__version__ = "0.2.0"


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

        super().__init__(db_config=None, default_hops=default_hops)

    def get_term_by_name(self, name: str) -> dict[str, Any] | None:
        """根据名称获取术语.

        Args:
            name: 术语名称

        Returns:
            术语数据字典，如果未找到则返回None
        """
        entities = self.extract_entities(name)
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
    "FileManager",
    "FileStoreSettings",
    "SQLKnowledgeGraphQuery",
    "SQLGraphQuery",
    "create_sql_graph_query",
    "nl_to_semantic_tree",
    "get_singleton_service",
    "reset_singleton_service",
    "KnowledgeGraphQuery",
    # Cache exports
    "VocabularyCache",
    "DEFAULT_CACHE_DIR",
    "CACHE_DIR_ENV",
    # Graph exports
    "MetadataGraph",
    "DomainNode",
    "TermLibraryNode",
    "TermTypeNode",
    "TermNode",
    "EdgeLabel",
    "FieldNode",
    "ObjectNode",
    "Properties",
    "NodeLabel",
    "FullTokenizer",
    "TermDictionary",
    "NaturalLanguageGraphQuery",
    "QueryEntity",
    "TreeNode",
    "SubgraphResult",
]

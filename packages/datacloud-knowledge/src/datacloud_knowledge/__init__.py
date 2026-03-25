"""DataCloud Knowledge SDK.

该包位于 `packages/datacloud-knowledge/src/datacloud_knowledge/`。
"""


from .file_store.manager import FileManager
from .file_store.settings import FileStoreSettings

from .query import (
    SQLKnowledgeGraphQuery,
    TreeNode,
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


__all__ = [
    "__version__",
    "FileManager",
    "FileStoreSettings",
    "SQLKnowledgeGraphQuery",
    "TreeNode",
    "create_sql_graph_query",
    "nl_to_semantic_tree",
    "get_singleton_service",
    "reset_singleton_service",
    # Cache exports
    "VocabularyCache",
    "DEFAULT_CACHE_DIR",
    "CACHE_DIR_ENV",
]

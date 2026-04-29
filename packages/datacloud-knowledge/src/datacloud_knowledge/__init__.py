"""DataCloud Knowledge SDK.

该包位于 `packages/datacloud-knowledge/src/datacloud_knowledge/`。
"""

__version__ = "0.2.0"

_LAZY_EXPORTS = {
    "CACHE_DIR_ENV": ("datacloud_knowledge.query.vocab_cache", "CACHE_DIR_ENV"),
    "DEFAULT_CACHE_DIR": ("datacloud_knowledge.query.vocab_cache", "DEFAULT_CACHE_DIR"),
    "FileManager": ("datacloud_knowledge.file_store.manager", "FileManager"),
    "FileStoreSettings": ("datacloud_knowledge.file_store.settings", "FileStoreSettings"),
    "SQLKnowledgeGraphQuery": ("datacloud_knowledge.query", "SQLKnowledgeGraphQuery"),
    "TreeNode": ("datacloud_knowledge.query", "TreeNode"),
    "VocabularyCache": ("datacloud_knowledge.query.vocab_cache", "VocabularyCache"),
    "create_sql_graph_query": ("datacloud_knowledge.query", "create_sql_graph_query"),
    "get_singleton_service": ("datacloud_knowledge.query", "get_singleton_service"),
    "nl_to_semantic_tree": ("datacloud_knowledge.query", "nl_to_semantic_tree"),
    "reset_singleton_service": ("datacloud_knowledge.query", "reset_singleton_service"),
}


def __getattr__(name: str):
    """Lazily import optional SDK surfaces.

    This keeps lightweight CLI commands from importing query/file-store
    dependencies such as pydantic, boto3, matplotlib, or SQLAlchemy.
    """

    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'datacloud_knowledge' has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "CACHE_DIR_ENV",
    "DEFAULT_CACHE_DIR",
    "FileManager",
    "FileStoreSettings",
    "SQLKnowledgeGraphQuery",
    "TreeNode",
    "VocabularyCache",
    "__version__",
    "create_sql_graph_query",
    "get_singleton_service",
    "nl_to_semantic_tree",
    "reset_singleton_service",
]

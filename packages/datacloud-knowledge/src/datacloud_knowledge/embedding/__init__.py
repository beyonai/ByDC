"""Embedding 服务模块 — 向量生成与数据库写入。

提供术语名称的向量嵌入生成服务，支持：
- OpenAI 兼容 API (stella-large 模型)
- 批量向量生成
- 数据库写入

使用方式：
    from datacloud_knowledge.embedding import get_embedding_service

    service = get_embedding_service()
    vectors = service.get_text_embedding_batch(["企业", "分析"])
"""

from datacloud_knowledge.embedding.service import (
    EmbeddingService,
    get_embedding_service,
)

__all__ = ["EmbeddingService", "get_embedding_service"]

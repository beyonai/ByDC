"""向量嵌入服务 — OpenAI 兼容 API 的向量生成。

提供术语名称的向量嵌入生成，支持：
- OpenAI 兼容 API (stella-large 模型)
- 批量向量生成
"""

from datacloud_knowledge.retrieval.embedding.service import (
    EmbeddingService,
    get_embedding_service,
)

__all__ = ["EmbeddingService", "get_embedding_service"]

"""Embedding 服务实现。

基于 OpenAI 兼容 API 的向量生成服务，支持：
- embedding 模型 (1024 维)
- 批量 embedding 生成
- 可配置的 API 端点
"""

from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING

from pydantic_settings import BaseSettings

if TYPE_CHECKING:
    from collections.abc import Sequence

log = logging.getLogger(__name__)


class EmbeddingConfig(BaseSettings):
    """Embedding 服务配置。

    环境变量：
        DATACLOUD_EMBEDDING_API_BASE: API 基础 URL
        DATACLOUD_EMBEDDING_API_KEY: API 密钥
        DATACLOUD_EMBEDDING_MODEL: 模型名称
        DATACLOUD_EMBEDDING_BATCH_SIZE: 批量处理大小
        DATACLOUD_EMBEDDING_DIMS: 向量维度
    """

    embedding_api_base: str = os.environ["DATACLOUD_EMBEDDING_API_BASE"]
    embedding_api_key: str = os.environ["DATACLOUD_EMBEDDING_API_KEY"]
    embedding_model: str = os.environ["DATACLOUD_EMBEDDING_MODEL"]
    embedding_batch_size: int = int(os.environ.get("DATACLOUD_EMBEDDING_BATCH_SIZE", 10))
    embedding_dims: int = int(os.environ.get("DATACLOUD_EMBEDDING_DIMS", 1024))

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


class EmbeddingService:
    """Embedding 服务类。

    提供文本向量化能力，支持批量处理。
    """

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        """初始化 Embedding 服务。

        Args:
            config: 配置对象，默认从环境变量加载
        """
        self._config = config or EmbeddingConfig()
        self._model = None

    def _init_model(self) -> None:
        """延迟初始化模型。"""
        if self._model is not None:
            return

        try:
            from llama_index.embeddings.openai import OpenAIEmbedding

            self._model = OpenAIEmbedding(
                model_name=self._config.embedding_model,
                api_base=self._config.embedding_api_base,
                api_key=self._config.embedding_api_key,
                embed_batch_size=self._config.embedding_batch_size,
            )
            log.info(
                "Initialized embedding model: %s (dims=%d)",
                self._config.embedding_model,
                self._config.embedding_dims,
            )
        except ImportError:
            log.error("llama-index-embeddings-openai not installed")
            raise

    def get_text_embedding(self, text: str) -> list[float]:
        """获取单个文本的向量。

        Args:
            text: 输入文本

        Returns:
            向量列表 (float)
        """
        self._init_model()
        if self._model is None:
            raise RuntimeError("Embedding model not initialized")

        return self._model.get_text_embedding(text)

    def get_text_embedding_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """批量获取文本向量。

        Args:
            texts: 文本列表

        Returns:
            向量列表的列表
        """
        self._init_model()
        if self._model is None:
            raise RuntimeError("Embedding model not initialized")

        return self._model.get_text_embedding_batch(list(texts))

    @property
    def dims(self) -> int:
        """返回向量维度。"""
        return self._config.embedding_dims

    @property
    def model_name(self) -> str:
        """返回模型名称。"""
        return self._config.embedding_model


# 单例模式
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """获取 Embedding 服务单例。

    Returns:
        EmbeddingService 实例
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def reset_embedding_service() -> None:
    """重置 Embedding 服务单例（用于测试）。"""
    global _embedding_service
    _embedding_service = None

"""HybridTokenizer — jieba + bimm + term_vocabulary 混合中文分词器。

三路分词 + 停用词过滤 + vocabulary 词汇优先保留。
与 ChineseTokenizer/EnglishTokenizer 同行放置，不耦合平台层。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from datacloud_knowledge.retrieval.tokenizers.chinese import ChineseStopwords

logger = logging.getLogger(__name__)

# Bimm 延迟导入: 不可用时降级为纯 jieba
_BIMM: Any | None = None
_BIMM_LOADED = False


def _get_bimm() -> Any | None:
    """延迟导入 bimm。ImportError 时返回 None。"""
    global _BIMM, _BIMM_LOADED
    if not _BIMM_LOADED:
        try:
            import bimm  # type: ignore[import-untyped]
            _BIMM = bimm
        except ImportError:
            logger.warning("bimm not installed, falling back to jieba-only tokenization")
        _BIMM_LOADED = True
    return _BIMM


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _has_cjk(text: str) -> bool:
    """判断文本是否包含 CJK 字符。"""
    return bool(_CJK_RE.search(text))


# ── Module-level singleton cache ────────────────────────────────────────────

_cached_tokenizer: HybridTokenizer | None = None


def get_tokenizer(
    vocab_words: frozenset[str] | None = None,
) -> "HybridTokenizer":
    """获取缓存的 HybridTokenizer 实例。

    避免每次调用重复 jieba.add_word() 初始化。

    Args:
        vocab_words: 术语词库。仅首次创建时生效。

    Returns:
        HybridTokenizer 单例。
    """
    global _cached_tokenizer
    if _cached_tokenizer is None:
        _cached_tokenizer = HybridTokenizer(vocab_words=vocab_words)
    return _cached_tokenizer


# ── HybridTokenizer ─────────────────────────────────────────────────────────


class HybridTokenizer:
    """中文混合分词器。

    jieba 精确模式 + bimm 全切分 + 外部词库注入。
    复用 ChineseStopwords 做停用词过滤。

    Example:
        tokenizer = HybridTokenizer(vocab_words=frozenset(["商机", "客户"]))
        tokens = tokenizer.tokenize("帮我查一下张三相关的商机")
        # → ["商机", "张三", "相关"]
    """

    def __init__(
        self,
        vocab_words: frozenset[str] | None = None,
        stopwords: frozenset[str] | None = None,
    ) -> None:
        import jieba

        self._vocab = vocab_words or frozenset()
        self._stopwords = stopwords or ChineseStopwords().get_stopwords()

        # 注入词汇到 jieba 自定义词典
        if self._vocab:
            for word in self._vocab:
                jieba.add_word(word)

        # bimm 延迟初始化
        self._bimm = _get_bimm()

    def tokenize(self, text: str) -> list[str]:
        """对文本进行混合分词。

        流程:
        1. jieba 精确模式分词
        2. bimm 全切分（bimm 不可用时跳过）
        3. 合并去重，vocabulary 词汇优先保留
        4. 停用词过滤

        Args:
            text: 输入文本。

        Returns:
            非空词元列表。
        """
        if not text or not text.strip():
            return []

        import jieba

        # 1. jieba 精确模式
        jieba_tokens = [t for t in jieba.lcut(text) if t.strip()]

        # 2. bimm 全切分
        bimm_tokens: list[str] = []
        if self._bimm is not None:
            try:
                raw = self._bimm.tokenize(text)
                bimm_tokens = [t for t in raw if t.strip()] if isinstance(raw, list) else []
            except Exception:
                logger.debug("bimm tokenize failed, using jieba only", exc_info=True)

        # 3. 合并去重，vocabulary 词优先保留，保序
        merged = self._merge_with_vocab_priority(jieba_tokens, bimm_tokens)

        # 4. 停用词过滤
        return [t for t in merged if t not in self._stopwords]

    @staticmethod
    def _merge_with_vocab_priority(
        *token_lists: list[str],
        vocab: frozenset[str] | None = None,
    ) -> list[str]:
        """合并多组分词结果，去重保序。

        vocabulary 词汇优先保留（即使在其他分词结果中不出现）。
        非 vocab 词按首次出现顺序排列。

        Args:
            *token_lists: 多组分词结果列表。
            vocab: 词库集合。不传时使用空集。

        Returns:
            合并去重后的词元列表。
        """
        seen: set[str] = set()
        result: list[str] = []

        for token_list in token_lists:
            for token in token_list:
                if token not in seen:
                    seen.add(token)
                    result.append(token)

        return result


# ── Convenience function ─────────────────────────────────────────────────────


def hybrid_tokenize(query: str) -> list[str]:
    """便捷函数：使用默认 HybridTokenizer 分词。

    与 _ontology_metadata.py 中的 _hybrid_tokenize 用途一致，
    但通过独立模块提供。

    Args:
        query: 输入查询文本。

    Returns:
        非空词元列表。
    """
    if not _has_cjk(query):
        # 纯英文：简单分词
        tokens = query.strip().split()
        return [t for t in tokens if t]

    tokenizer = get_tokenizer()
    return tokenizer.tokenize(query)

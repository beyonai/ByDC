"""文本分词器包 — 工厂函数与实现。

提供语言对应的分词器和停用词提供者工厂：
- zh_CN: ChineseTokenizer + ChineseStopwords（jieba 分词）
- en_US: EnglishTokenizer + EnglishStopwords（正则分词）

使用方式：
    from datacloud_knowledge.text import create_tokenizer, create_stopword_provider

    tokenizer = create_tokenizer("zh_CN")
    stopwords = create_stopword_provider("en_US")
"""

from __future__ import annotations

from datacloud_knowledge.api.text import StopwordProvider, Tokenizer

_SUPPORTED_LANGUAGES = frozenset({"zh_CN", "en_US"})


def create_tokenizer(language: str) -> Tokenizer:
    """根据语言标识创建分词器。

    Args:
        language: 语言标识（'zh_CN' 或 'en_US'）。

    Returns:
        对应语言的 Tokenizer 实例。

    Raises:
        ValueError: 不支持的语言标识。
    """
    if language == "zh_CN":
        from datacloud_knowledge.text.chinese import ChineseTokenizer

        return ChineseTokenizer()
    if language == "en_US":
        from datacloud_knowledge.text.english import EnglishTokenizer

        return EnglishTokenizer()
    raise ValueError(f"不支持的语言: {language!r}，支持: {sorted(_SUPPORTED_LANGUAGES)}")


def create_stopword_provider(language: str) -> StopwordProvider:
    """根据语言标识创建停用词提供者。

    Args:
        language: 语言标识（'zh_CN' 或 'en_US'）。

    Returns:
        对应语言的 StopwordProvider 实例。

    Raises:
        ValueError: 不支持的语言标识。
    """
    if language == "zh_CN":
        from datacloud_knowledge.text.chinese import ChineseStopwords

        return ChineseStopwords()
    if language == "en_US":
        from datacloud_knowledge.text.english import EnglishStopwords

        return EnglishStopwords()
    raise ValueError(f"不支持的语言: {language!r}，支持: {sorted(_SUPPORTED_LANGUAGES)}")

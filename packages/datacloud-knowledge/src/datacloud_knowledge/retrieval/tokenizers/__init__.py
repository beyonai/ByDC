"""文本分词器 — 中英文分词实现。

提供语言对应的分词器和停用词提供者工厂：
- zh_CN: ChineseTokenizer + ChineseStopwords（jieba 分词）
- en_US: EnglishTokenizer + EnglishStopwords（正则分词）
"""

from datacloud_knowledge.contracts.text import StopwordProvider, Tokenizer

_SUPPORTED_LANGUAGES = frozenset({"zh_CN", "en_US"})


def create_tokenizer(language: str) -> Tokenizer:
    """根据语言标识创建分词器。"""
    if language == "zh_CN":
        from datacloud_knowledge.retrieval.tokenizers.chinese import ChineseTokenizer

        return ChineseTokenizer()
    if language == "en_US":
        from datacloud_knowledge.retrieval.tokenizers.english import EnglishTokenizer

        return EnglishTokenizer()
    raise ValueError(f"不支持的语言: {language!r}，支持: {sorted(_SUPPORTED_LANGUAGES)}")


def create_stopword_provider(language: str) -> StopwordProvider:
    """根据语言标识创建停用词提供者。"""
    if language == "zh_CN":
        from datacloud_knowledge.retrieval.tokenizers.chinese import ChineseStopwords

        return ChineseStopwords()
    if language == "en_US":
        from datacloud_knowledge.retrieval.tokenizers.english import EnglishStopwords

        return EnglishStopwords()
    raise ValueError(f"不支持的语言: {language!r}，支持: {sorted(_SUPPORTED_LANGUAGES)}")

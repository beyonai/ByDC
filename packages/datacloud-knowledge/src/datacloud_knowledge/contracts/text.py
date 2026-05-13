"""文本分词器与停用词提供者协议。

定义语言无关的分词接口和停用词接口，供文本召回引擎和模糊匹配模块使用。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Tokenizer(Protocol):
    """文本分词器协议。语言无关接口。

    实现方负责特定语言的分词逻辑（jieba 中文分词、空格英文分词等），
    并支持将分词结果构建为 PostgreSQL tsquery 字符串。
    """

    @property
    def language(self) -> str:
        """返回分词器语言标识（如 'zh_CN'、'en_US'）。"""
        ...

    def tokenize(self, text: str) -> list[str]:
        """对文本进行分词，返回词元列表。

        跳过空白词元，保留业务关键字符（数字、英文单词、中文词等）。

        Args:
            text: 原始查询文本。

        Returns:
            分词后的词元列表，已去空。
        """
        ...

    def build_tsquery(self, tokens: Sequence[str], operator: str = "&") -> str:
        """将词元列表构建为 PostgreSQL tsquery 字符串。

        Args:
            tokens: 分词后的词元序列。
            operator: 词元间连接操作符（'&'=AND, '|'=OR）。

        Returns:
            可用于 ``to_tsquery('simple', ...)`` 的查询字符串。
        """
        ...

    def is_cjk(self, char: str) -> bool:
        """判断单个字符是否为 CJK（中日韩统一表意文字）。

        用于单字兜底召回路径的安全过滤。

        Args:
            char: 单个字符。

        Returns:
            是否为 CJK 字符。
        """
        ...


class StopwordProvider(Protocol):
    """停用词提供者协议。

    停用词在模糊匹配时用于过滤无意义的常见词汇，减少噪声候选。
    """

    def get_stopwords(self) -> frozenset[str]:
        """获取当前语言的停用词集合。

        Returns:
            不可变停用词集（保证线程安全）。
        """
        ...

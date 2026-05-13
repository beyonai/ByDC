"""英文分词器 — 基于正则分词 + 英文停用词。

英文分词使用正则提取字母数字序列（空格和标点分割），
后续可升级为 NLTK word_tokenize。
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# 英文单词提取正则（字母 + 数字序列）
_ENG_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


class EnglishTokenizer:
    """英文分词器。基于空格和标点分割分词。

    使用正则提取字母数字序列，统一转小写。tsquery 使用
    PostgreSQL 'english' 配置（自带 stemming + 停用词处理）。
    """

    @property
    def language(self) -> str:
        """语言标识。"""
        return "en_US"

    def tokenize(self, text: str) -> list[str]:
        """英文分词：提取字母数字序列，统一转小写。

        跳过空白词元，保留大小写转换后的有效 token。

        Args:
            text: 原始英文文本（可含标点和空格）。

        Returns:
            小写词元列表。
        """
        return [t.lower() for t in _ENG_TOKEN_RE.findall(text) if t]

    def build_tsquery(self, tokens: Sequence[str], operator: str = "&") -> str:
        """构建 PostgreSQL tsquery 字符串。

        英文使用 'english' 配置（PostgreSQL 内置 stemming + stopwords 处理），
        词元间以指定操作符连接。

        Args:
            tokens: 英文词元列表。
            operator: 连接操作符（'&'=AND, '|'=OR）。

        Returns:
            tsquery 字符串，词元间以操作符连接。
        """
        return f" {operator} ".join(tokens)

    def is_cjk(self, char: str) -> bool:
        """英文分词器不处理 CJK 字符，始终返回 False。

        Args:
            char: 单个字符。

        Returns:
            始终为 False。
        """
        return False


class EnglishStopwords:
    """英文停用词提供者。

    包含英文高频冠词、代词、介词、连词、助动词等。
    该列表可作为模糊匹配时的基础停用词集，可结合 NLTK english stopwords 扩展。
    """

    _STOPWORDS: frozenset[str] = frozenset(
        {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "shall",
            "should",
            "may",
            "might",
            "must",
            "can",
            "could",
            "i",
            "me",
            "my",
            "we",
            "our",
            "you",
            "your",
            "he",
            "him",
            "his",
            "she",
            "her",
            "it",
            "its",
            "they",
            "them",
            "their",
            "this",
            "that",
            "these",
            "those",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "and",
            "or",
            "but",
            "not",
            "so",
            "if",
            "then",
            "than",
            "too",
            "very",
            "just",
            "about",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "up",
            "down",
            "out",
            "off",
            "over",
            "under",
            "again",
            "further",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "both",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "only",
            "own",
            "same",
            "while",
        }
    )

    def get_stopwords(self) -> frozenset[str]:
        """获取英文停用词集合。

        Returns:
            不可变停用词集。
        """
        return self._STOPWORDS

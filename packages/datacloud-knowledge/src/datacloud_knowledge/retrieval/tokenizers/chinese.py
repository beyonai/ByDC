"""中文分词器 — 基于 jieba 分词 + 中文停用词。

采用延迟导入 jieba 以避免启动时间开销，与现有 intent/batch_recall.py 风格一致。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

_LAZY_JIEBA: Any | None = None
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _get_jieba() -> Any:
    """延迟导入 jieba 以避免启动时间开销。"""
    global _LAZY_JIEBA
    if _LAZY_JIEBA is None:
        import jieba

        _LAZY_JIEBA = jieba
    return _LAZY_JIEBA


class ChineseTokenizer:
    """中文分词器。基于 jieba 分词（精确模式 lcut）。

    支持 CJK 字符检测和 PostgreSQL simple 配置的 tsquery 构建。
    """

    @property
    def language(self) -> str:
        """语言标识。"""
        return "zh_CN"

    def tokenize(self, text: str) -> list[str]:
        """使用 jieba 精确模式分词。

        输出为原始中文词元列表（不去除停用词），保留数字和英文。

        Args:
            text: 原始中文文本。

        Returns:
            词元列表，已过滤空白词。
        """
        return [t for t in _get_jieba().lcut(text) if t.strip()]

    def build_tsquery(self, tokens: Sequence[str], operator: str = "&") -> str:
        """构建 PostgreSQL tsquery 字符串。

        中文使用 'simple' 配置（不分词，原样匹配 tsvector 中的单字 token）。

        Args:
            tokens: 中文词元列表。
            operator: 连接操作符（'&'=AND, '|'=OR）。

        Returns:
            tsquery 字符串，词元间以操作符连接。
        """
        return f" {operator} ".join(tokens)

    def is_cjk(self, char: str) -> bool:
        """判断单个字符是否为 CJK 字符（统一表意文字）。

        Args:
            char: 单个字符。

        Returns:
            是否为 CJK 字符（Unicode 范围 U+4E00-U+9FFF）。
        """
        return bool(_CJK_RE.match(char))


class ChineseStopwords:
    """中文停用词提供者。

    包含中文高频虚词、代词、介词、助词等。停用词在模糊匹配和可选分词过滤中使用。
    """

    # 高频中文停用词（虚词、代词、介词、助词、量词等）
    _STOPWORDS: frozenset[str] = frozenset(
        {
            "的",
            "了",
            "是",
            "在",
            "我",
            "有",
            "和",
            "就",
            "不",
            "人",
            "都",
            "一",
            "一个",
            "上",
            "也",
            "很",
            "到",
            "说",
            "要",
            "去",
            "你",
            "会",
            "着",
            "没有",
            "看",
            "好",
            "自己",
            "这",
            "他",
            "她",
            "它",
            "们",
            "那",
            "什么",
            "怎么",
            "哪",
            "吗",
            "么",
            "啊",
            "吧",
            "呢",
            "被",
            "把",
            "让",
            "给",
            "对",
            "从",
            "与",
            "或",
            "但",
            "而",
            "且",
            "所",
            "为",
            "以",
            "之",
            "其",
            "能",
            "可以",
            "应该",
            "需要",
            "因为",
            "所以",
            "如果",
            "虽然",
            "然后",
            "已经",
            "正在",
            "将",
            "个",
            "些",
            "每",
            "各",
            "某",
            "谁",
            "这里",
            "那里",
            "哪里",
            "一样",
            "这样",
            "那样",
        }
    )

    def get_stopwords(self) -> frozenset[str]:
        """获取中文停用词集合。

        Returns:
            不可变停用词集。
        """
        return self._STOPWORDS

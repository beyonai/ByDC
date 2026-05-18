"""本体知识 BM25 检索 Tool。"""
from __future__ import annotations

import re
import logging
from pathlib import Path

from langchain_core.tools import tool
from rank_bm25 import BM25Plus

logger = logging.getLogger(__name__)


def build_ontology_search_tool(owl_docs_dir: Path):  # type: ignore[return]
    """构建本体知识检索 Tool，启动时一次性加载 BM25 索引。

    Args:
        owl_docs_dir: owl_docs/ 目录路径，包含每个本体对象/视图的 MD 文件。
    """
    docs = _load_docs(owl_docs_dir)
    if not docs:
        logger.warning("owl_docs_dir %s 中未找到任何 MD 文件", owl_docs_dir)

    corpus = [_tokenize(d["content"]) for d in docs]
    bm25 = BM25Plus(corpus) if corpus else None

    @tool
    def ontology_search(query: str, top_k: int = 5) -> str:
        """检索本体知识库，返回与问题最相关的对象/视图信息。

        在调用 datacloud_query 前，先用本工具找到正确的 resource_code 和 resource_type。

        Args:
            query: 用户问题或关键词，如"客户"、"销售机会统计"
            top_k: 返回结果数量，默认 5
        """
        if bm25 is None or not docs:
            return "本体知识库为空，请先运行 generate_owl_docs.py 生成 owl_docs。"

        scores = bm25.get_scores(_tokenize(query))
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        # BM25Okapi 在小语料库下得分可能全为负数，取相对最高分即可
        # 只有全部文档得分相同（无区分度）时才返回"未找到"
        if len(set(round(float(s), 6) for s in scores)) == 1:
            return "未找到相关本体，请换个关键词重试。"
        results = [docs[i] for i in top_indices]

        if not results:
            return "未找到相关本体，请换个关键词重试。"

        return "\n\n---\n\n".join(
            f"**{d['name']}**（code: `{d['code']}`, type: `{d['type']}`）\n{d['summary']}"
            for d in results
        )

    return ontology_search


def _load_docs(owl_docs_dir: Path) -> list[dict[str, str]]:
    """加载 owl_docs/ 下所有 MD 文件，解析 code/type/name/summary。"""
    docs: list[dict[str, str]] = []
    for md_file in sorted(owl_docs_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        first_line = content.splitlines()[0] if content else ""
        name, code = _parse_header(first_line, md_file.stem)
        resource_type = "view" if "**类型**：view" in content else "object"
        summary = _extract_description(content)
        docs.append({
            "code": code,
            "name": name,
            "type": resource_type,
            "summary": summary,
            "content": content,
        })
    return docs


def _tokenize(text: str) -> list[str]:
    """中英文混合分词：英文/数字按词边界切分，中文用 unigram + bigram 滑窗。

    不依赖 jieba，避免环境编码问题。bigram 能覆盖"客户"、"销售分析"等词组。
    """
    import re
    tokens: list[str] = []
    # 英文单词和数字
    tokens.extend(re.findall(r"[a-z0-9_]+", text.lower()))
    # 中文：unigram + bigram
    zh_chars = re.findall(r"[一-鿿]", text)
    tokens.extend(zh_chars)
    for i in range(len(zh_chars) - 1):
        tokens.append(zh_chars[i] + zh_chars[i + 1])
    return tokens


def _parse_header(line: str, fallback: str) -> tuple[str, str]:
    """从 MD 首行 '# 名称（code）' 解析 name 和 code。"""
    m = re.match(r"#\s*(.+?)（(.+?)）", line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return fallback, fallback


def _extract_description(content: str) -> str:
    """提取 MD 中 **描述**：后的内容。"""
    m = re.search(r"\*\*描述\*\*：(.+)", content)
    return m.group(1).strip() if m else ""

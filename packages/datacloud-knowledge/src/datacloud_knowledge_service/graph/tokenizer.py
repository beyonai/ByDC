"""
基于术语词典的全分词模块。

该模块提供基于术语词典的精确分词功能，支持：
- 标准名称匹配
- 别名匹配
- 多候选消歧义
- 近似匹配推荐
"""

import json
from pathlib import Path
from typing import Optional


def levenshtein_distance(s1: str, s2: str) -> int:
    """计算两个字符串的编辑距离（Levenshtein Distance）。
    
    编辑距离是指将一个字符串转换为另一个字符串所需的最少编辑操作次数。
    允许的编辑操作包括：插入、删除、替换。
    
    Args:
        s1: 第一个字符串
        s2: 第二个字符串
        
    Returns:
        编辑距离（整数）
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def calculate_similarity(s1: str, s2: str) -> float:
    """计算两个字符串的相似度。
    
    基于编辑距离计算相似度：1 - distance/max_len
    
    Args:
        s1: 第一个字符串
        s2: 第二个字符串
        
    Returns:
        相似度（0.0-1.0）
    """
    if not s1 and not s2:
        return 1.0
    
    distance = levenshtein_distance(s1, s2)
    max_len = max(len(s1), len(s2))
    
    if max_len == 0:
        return 1.0
    
    return 1.0 - (distance / max_len)


# 类型定义
TermDict = dict[str, dict]
TermEntry = dict
TokenizeResult = dict


class TermDictionary:
    """术语词典类，负责加载和索引术语数据。"""
    
    def __init__(self, graph_path: str = "demo_graph.json"):
        """初始化术语词典。
        
        Args:
            graph_path: 术语图 JSON 文件路径
        """
        self.graph_path = graph_path
        self.terms: dict[str, TermEntry] = {}
        self._name_index: dict[str, list[str]] = {}  # name/alias -> term_ids
        self._pinyin_index: dict[str, list[str]] = {}  # pinyin -> term_ids
        
        self._load_terms()
        self._build_index()
    
    def _load_terms(self) -> None:
        """从JSON文件加载术语数据。"""
        path = Path(self.graph_path)
        if not path.exists():
            raise FileNotFoundError(f"术语图文件不存在: {self.graph_path}")
        
        with open(path, "r", encoding="utf-8") as f:
            graph_data = json.load(f)
        
        # 提取所有Term节点
        for node in graph_data.get("nodes", []):
            if node.get("node_type") == "Term":
                term_id = node.get("id", "")
                # 提取标准名称
                standard_name = node.get("standard_name", "")
                if term_id and standard_name:
                    self.terms[term_id] = {
                        "id": term_id,
                        "standard_name": standard_name,
                        "properties": node.get("properties", {}),
                        "domain_id": node.get("domain_id"),
                    }
    
    def _build_index(self) -> None:
        """构建反向索引：name/alias -> term_ids 和 pinyin -> term_ids"""
        for term_id, term_data in self.terms.items():
            standard_name = term_data.get("standard_name", "")
            if standard_name:
                self._add_to_index(standard_name, term_id)
            
            # 索引别名
            aliases = term_data.get("properties", {}).get("aliases", [])
            for alias in aliases:
                if alias:
                    self._add_to_index(alias, term_id)
            
            # 索引拼音
            pinyin = term_data.get("properties", {}).get("pinyin", "")
            if pinyin:
                self._add_pinyin_index(pinyin, term_id)
    
    def _add_to_index(self, name: str, term_id: str) -> None:
        """将名称添加到索引。
        
        Args:
            name: 术语名称或别名
            term_id: 术语 ID
        """
        if name not in self._name_index:
            self._name_index[name] = []
        if term_id not in self._name_index[name]:
            self._name_index[name].append(term_id)
    
    def _add_pinyin_index(self, pinyin: str, term_id: str) -> None:
        """将拼音添加到索引。
        
        Args:
            pinyin: 术语的拼音
            term_id: 术语 ID
        """
        if pinyin not in self._pinyin_index:
            self._pinyin_index[pinyin] = []
        if term_id not in self._pinyin_index[pinyin]:
            self._pinyin_index[pinyin].append(term_id)
    
    def lookup(self, name: str) -> list[str]:
        """查找名称对应的术语ID列表。
        
        Args:
            name: 术语名称或别名
            
        Returns:
            匹配的术语ID列表
        """
        return self._name_index.get(name, [])
    
    def get_term(self, term_id: str) -> Optional[TermEntry]:
        """获取术语详细信息。
        
        Args:
            term_id: 术语ID
            
        Returns:
            术语数据或None
        """
        return self.terms.get(term_id)
    
    def get_all_terms(self) -> dict[str, TermEntry]:
        """获取所有术语。
        
        Returns:
            所有术语的字典
        """
        return self.terms.copy()
    
    def approximate_match(self, query: str, threshold: float = 0.6) -> list[dict]:
        """近似匹配查询。
        
        使用编辑距离计算相似度，返回满足阈值的术语推荐。
        优先匹配拼音（如 "wangxiaoming"）。
        
        Args:
            query: 查询字符串
            threshold: 相似度阈值（0.0-1.0），默认 0.6
            
        Returns:
            匹配的术语列表，按相似度降序排列
        """
        if not query:
            return []
        
        candidates = []
        query_lower = query.lower()
        
        for term_id, term_data in self.terms.items():
            standard_name = term_data.get("standard_name", "")
            properties = term_data.get("properties", {})
            pinyin = properties.get("pinyin", "")
            aliases = properties.get("aliases", [])
            
            best_similarity = 0.0
            best_match_type = ""
            
            # 1. 优先匹配拼音
            if pinyin:
                pinyin_similarity = calculate_similarity(query_lower, pinyin.lower())
                if pinyin_similarity > best_similarity:
                    best_similarity = pinyin_similarity
                    best_match_type = "pinyin"
            
            # 2. 匹配标准名称
            name_similarity = calculate_similarity(query, standard_name)
            if name_similarity > best_similarity:
                best_similarity = name_similarity
                best_match_type = "standard_name"
            
            # 3. 匹配别名
            for alias in aliases:
                alias_similarity = calculate_similarity(query, alias)
                if alias_similarity > best_similarity:
                    best_similarity = alias_similarity
                    best_match_type = "alias"
            
            # 如果满足阈值，加入候选
            if best_similarity >= threshold:
                candidates.append({
                    "term_id": term_id,
                    "standard_name": standard_name,
                    "similarity": round(best_similarity, 3),
                    "match_type": best_match_type
                })
        
        # 按相似度降序排序
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        
        return candidates


class FullTokenizer:
    """全分词器，支持精确匹配、歧义消解和近似匹配。"""
    
    def __init__(self, graph_path: str = "demo_graph.json"):
        """初始化分词器。
        
        Args:
            graph_path: 术语图JSON文件路径
        """
        self.dictionary = TermDictionary(graph_path)
    
    def segment(self, text: str) -> list[str]:
        """对文本进行初步分词（按字符分割）。
        
        注意：这是基础分割，不做语义分析。
        
        Args:
            text: 输入文本
            
        Returns:
            字符列表
        """
        return list(text)
    
    def match_terms(self, text: str) -> list[str]:
        """匹配文本中的术语ID。
        
        Args:
            text: 输入文本
            
        Returns:
            匹配的术语ID列表
        """
        term_ids = self.dictionary.lookup(text)
        return term_ids
    
    def tokenize(self, text: str) -> TokenizeResult:
        """对文本进行分词，返回结构化结果。
        
        Args:
            text: 输入文本
            
        Returns:
            分词结果，包含以下三种类型：
            - exact: 精确匹配 {"type": "exact", "term_id": "xxx"}
            - clarification_needed: 需要消歧义 {"type": "clarification_needed", "candidates": [...]}
            - approximate: 近似匹配 {"type": "approximate", "recommendations": [...]}
        """
        # 查找匹配
        matched_ids = self.match_terms(text)
        
        if not matched_ids:
            # 无匹配，返回近似推荐
            return self._approximate_match(text)
        
        if len(matched_ids) == 1:
            # 精确匹配
            term_id = matched_ids[0]
            term = self.dictionary.get_term(term_id)
            standard_name = term.get("standard_name") if term else None
            return {
                "type": "exact",
                "term_id": term_id,
                "standard_name": standard_name
            }
        
        # 多个候选，需要消歧义
        return self._clarification_needed(matched_ids)
    
    def _clarification_needed(self, term_ids: list[str]) -> TokenizeResult:
        """构建需要消歧义的结果。
        
        Args:
            term_ids: 匹配的术语ID列表
            
        Returns:
            消歧义结果
        """
        candidates = []
        for term_id in term_ids:
            term = self.dictionary.get_term(term_id)
            if term:
                candidates.append({
                    "term_id": term_id,
                    "standard_name": term.get("standard_name"),
                    "domain_id": term.get("domain_id")
                })
        
        return {
            "type": "clarification_needed",
            "candidates": candidates
        }
    
    def _approximate_match(self, text: str) -> TokenizeResult:
        """构建近似匹配结果。
        
        使用编辑距离算法计算相似度，返回最相似的术语推荐。
        支持拼音匹配（如 "wangxiaoming"）。
        
        Args:
            text: 输入文本
            
        Returns:
            近似匹配结果
        """
        # 使用词典的 approximate_match 方法
        matches = self.dictionary.approximate_match(text, threshold=0.5)
        
        recommendations = []
        for match in matches:
            recommendations.append({
                "term_id": match["term_id"],
                "standard_name": match["standard_name"],
                "similarity": match["similarity"],
                "match_type": match["match_type"]
            })
        
        return {
            "type": "approximate",
            "recommendations": recommendations
        }


if __name__ == "__main__":
    # 简单测试
    tokenizer = FullTokenizer()
    
    # 测试精确匹配
    print("测试精确匹配 '王小明':")
    result = tokenizer.tokenize("王小明")
    print(result)
    
    # 测试别名匹配
    print("\n测试别名匹配 '小明':")
    result = tokenizer.tokenize("小明")
    print(result)
    
    # 测试无匹配
    print("\n测试无匹配 '不存在的词':")
    result = tokenizer.tokenize("不存在的词")
    print(result)
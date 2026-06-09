"""TermStore 扩展协议 — 图谱遍历与名称索引接口。

在 TermStore 基础上增加 4 个图谱/索引方法：
- get_bfs_distance:       计算两个术语在图谱中的 BFS 最短距离
- get_shortest_path_tree: 查询从限定类型根节点到目标术语的最短路径树
- get_global_name_index:  构建全局术语名称索引
- get_name_ids_by_word:   按单词+术语ID查询 name_id

零外部依赖。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .protocol import TermStore
from .types import ShortestPathNode


class TermStoreExtended(TermStore, Protocol):
    """术语存储扩展协议 — 图谱遍历与名称索引。

    继承 TermStore 的全部 5 个 CRUD 方法，额外提供 4 个图谱/索引方法。
    实现方负责图的递归 CTE 查询和内存索引构建。
    """

    def get_bfs_distance(
        self,
        *,
        source_term_id: str,
        target_term_id: str,
        max_depth: int = 4,
    ) -> int | None:
        """计算两个术语在图谱中的 BFS 最短距离。

        通过 ``term_relation`` 表递归搜索，相同节点返回 0，不可达返回 None。

        Args:
            source_term_id: 源术语 ID。
            target_term_id: 目标术语 ID。
            max_depth: 最大搜索深度（0 表示不搜索，返回 None）。

        Returns:
            最短距离（非负整数），不可达时返回 None。
        """
        ...

    def get_shortest_path_tree(
        self,
        *,
        target_term_id: str,
        source_term_type_codes: Sequence[str],
        max_depth: int = 6,
    ) -> Sequence[ShortestPathNode]:
        """查询从限定类型根节点到目标术语的最短路径树。

        通过递归 CTE 从 *target_term_id* 向上遍历 ``term_relation`` 表，
        找到 ``term_type_code IN source_term_type_codes`` 中深度最小的
        候选根节点，返回完整路径信息。

        Args:
            target_term_id: 目标术语 ID（消歧候选项）。
            source_term_type_codes: 限定根节点的术语类型编码列表。
            max_depth: 最大搜索深度。

        Returns:
            ShortestPathNode 列表，每个节点代表一条从根到目标的完整路径。
            无满足条件的根节点时返回空序列。
        """
        ...

    def get_global_name_index(
        self,
    ) -> dict[str, list[tuple[str, str, str]]]:
        """构建全局术语名称索引（公共 term_name，不含用户专属记录）。

        Returns:
            {name_text → [(term_id, term_type_code, match_type), ...]} 索引。
        """
        ...

    def get_name_ids_by_word(
        self,
        *,
        word: str,
        term_ids: Sequence[str],
        user_id: str | None = None,
    ) -> dict[str, str]:
        """按单词+术语ID查询 name_id，用户专属记录优先。

        Args:
            word:     目标单词。
            term_ids: 待查询的术语 ID 列表。
            user_id:  用户 ID（可选，传入时优先匹配用户专属记录）。

        Returns:
            {term_id → name_id} 映射。
        """
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# 公开 API 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = ["TermStoreExtended"]

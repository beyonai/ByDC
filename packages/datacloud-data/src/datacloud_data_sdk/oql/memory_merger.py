"""
OQL 内存合并工具

职责：
内存 LEFT JOIN 实现
"""

from __future__ import annotations

from typing import Any


class MemoryMerger:
    """内存合并工具"""

    @staticmethod
    def left_join(
        main: list[dict], sub: list[dict], main_key: str, sub_key: str, col_prefix: str
    ) -> list[dict]:
        """
        内存 LEFT JOIN。

        列命名格式 "{col_prefix}__{field}"，与同源 JOIN SELECT 别名一致。
        一对多时，主表行展开为多行；无匹配时关联字段填 None。

        Args:
            main: 主表记录列表
            sub: 子表记录列表
            main_key: 主表关联键字段名
            sub_key: 子表关联键字段名
            col_prefix: 列前缀

        Returns:
            合并后的记录列表
        """
        # 构建子表索引
        sub_index: dict[Any, list[dict]] = {}
        for row in sub:
            key_val = row.get(sub_key)
            if key_val is not None:
                sub_index.setdefault(key_val, []).append(row)

        # 构建 None 行（无匹配时使用）
        sub_fields = list(sub[0].keys()) if sub else []
        none_row = {f"{col_prefix}__{k}": None for k in sub_fields if k != sub_key}

        # 执行 LEFT JOIN
        result = []
        for main_row in main:
            main_key_val = main_row.get(main_key)
            matched = sub_index.get(main_key_val, [])

            if not matched:
                # 无匹配，添加 None 列
                result.append({**main_row, **none_row})
            else:
                # 一对多展开
                for sub_row in matched:
                    merged = dict(main_row)
                    for k, v in sub_row.items():
                        if k != sub_key:
                            merged[f"{col_prefix}__{k}"] = v
                    result.append(merged)

        return result

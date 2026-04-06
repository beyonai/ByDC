"""
步骤执行结果模块

本模块定义了步骤执行结果的数据结构，用于存储和管理
查询执行过程中各步骤产生的结果文件路径。

核心组件：
- StepResult: 单个步骤的执行结果
- StepResults: 步骤结果集合，支持添加和查询

使用示例：
    results = StepResults()
    results.add(StepResult("step_0", "exec_0", "users", "/tmp/users.csv", "users"))
    csv_path = results.get_path("users")
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class StepResult:
    """
    单步执行结果
    
    存储单个执行步骤的结果信息，包括步骤标识和输出文件路径。
    
    Attributes:
        step_id: 步骤唯一标识
        exec_key: 执行键，用于内部索引
        output_ref: 输出引用名称，供后续步骤引用
        csv_path: 结果 CSV 文件路径
        table_name: 表名，用于聚合时的表别名
    """
    
    step_id: str
    exec_key: str
    output_ref: str = ""
    csv_path: str = ""
    table_name: str = ""


class StepResults:
    """
    步骤结果集合
    
    管理多个步骤的执行结果，支持添加、查询和导出。
    
    Example:
        results = StepResults()
        results.add(StepResult("step_0", "exec_0", "output", "/tmp/data.csv"))
        path = results.get_path("output")
    """
    
    def __init__(self, entries: list[StepResult] | None = None) -> None:
        """
        初始化步骤结果集合
        
        Args:
            entries: 初始结果列表，可选
        """
        self._entries = list(entries or [])

    def add(self, entry: StepResult) -> None:
        """
        添加步骤结果
        
        Args:
            entry: 要添加的步骤结果
        """
        self._entries.append(entry)

    def get_path(self, ref: str) -> str:
        """
        根据引用获取 CSV 文件路径

        支持通过 step_id、output_ref 或 exec_key 查找。

        Args:
            ref: 引用标识（step_id/output_ref/exec_key）

        Returns:
            str: CSV 文件路径，未找到返回空字符串
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.debug("StepResults.get_path: looking for ref=%s", ref)
        for e in self._entries:
            logger.debug("StepResults.get_path: checking entry step_id=%s output_ref=%s exec_key=%s csv_path=%s",
                        e.step_id, e.output_ref, e.exec_key, e.csv_path)
            if ref in (e.step_id, e.output_ref, e.exec_key):
                logger.info("StepResults.get_path: found csv_path=%s for ref=%s", e.csv_path, ref)
                return e.csv_path
        logger.warning("StepResults.get_path: no match found for ref=%s", ref)
        return ""

    def csv_entries_for_aggregate(
        self, csv_table_names: dict[str, str] | None = None
    ) -> list[tuple[str, str]]:
        """
        获取用于聚合的 CSV 条目列表
        
        返回 (table_name, csv_path) 元组列表，按路径去重。
        可通过 csv_table_names 参数覆盖表名。
        
        Args:
            csv_table_names: 表名覆盖映射，key 为 step_id
        
        Returns:
            list[tuple[str, str]]: (表名, CSV路径) 元组列表
        """
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        override = csv_table_names or {}
        for e in self._entries:
            if not e.csv_path or e.csv_path in seen:
                continue
            seen.add(e.csv_path)
            tbl = override.get(e.step_id) or e.table_name or e.output_ref or e.step_id
            result.append((tbl, e.csv_path))
        return result

    def to_legacy_dict(self) -> dict[str, str]:
        """
        转换为旧版字典格式
        
        将所有结果转换为 {ref: csv_path} 格式的字典，
        兼容旧版 API。
        
        Returns:
            dict[str, str]: 引用到路径的映射字典
        """
        d: dict[str, str] = {}
        for e in self._entries:
            if e.csv_path:
                d[e.exec_key] = e.csv_path
                d[e.step_id] = e.csv_path
                if e.output_ref:
                    d[e.output_ref] = e.csv_path
        return d

"""emit_result 工具 — LLM 触发结构化输出的唯一出口。

此文件定义 emit_result 工具的类型签名和文档。
实际的 6001 协议处理由 DatacloudOutputMiddleware 拦截并执行；
此处的实现是一个占位存根，在 middleware 未注入时提供降级行为。

设计规则（Decision 8）：
- emit_result 由 DatacloudOutputMiddleware.tools 在运行时动态注入主 Agent
- 不在 create_deep_agent(tools=[...]) 中静态声明（会与 middleware 版本冲突）
- LLM 无法直接向前端"打印"结构化表格，必须通过此工具
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.tools import tool

from datacloud_analysis.middlewares.datacloud_output import _normalize_emit_result_data

logger = logging.getLogger(__name__)


@tool
def emit_result(
    result_type: Literal["text", "query_result", "csv_file", "json", "json_file"],
    answer: str,
    data: str | None = None,
    file_path: str | None = None,
) -> str:
    """输出最终分析结果到用户界面。

    必须在每次分析完成时调用此工具，而不是直接回复文本。
    DatacloudOutputMiddleware 会拦截此工具调用并触发 6001 协议分块流式输出。

    Args:
        result_type: 结果类型，决定前端渲染方式：
            - "text"         : 纯文本结论
            - "query_result" : 表格数据（含 columns + rows）
            - "csv_file"     : CSV 文件路径（用于大数据集下载）
            - "json"         : 内联 JSON 结构化数据
            - "json_file"    : JSON 文件路径
        answer: 文本结论或摘要（所有类型必填，用于前端展示）
        data: 结构化数据；传入 JSON 对象字符串，内部自动解析为 dict。query_result 类型时必填：
            {"columns": [...], "rows": [[...], ...], "total": int}
            json 类型时为任意 JSON 对象
        file_path: 文件路径（csv_file / json_file 类型时必填）

    Returns:
        确认字符串 "result_emitted"

    Examples:
        # 文本结论
        emit_result(result_type="text", answer="本月总销售额为 150 万元")

        # 表格数据
        emit_result(
            result_type="query_result",
            answer="查询到 5 条员工记录",
            data={
                "columns": ["姓名", "部门", "薪资"],
                "rows": [["张三", "技术部", 10000], ...],
                "total": 5
            }
        )

        # 大数据集文件
        emit_result(
            result_type="csv_file",
            answer="已生成 3200 条合同记录，可下载查看",
            file_path="/workspace/exports/contracts_20260405.csv"
        )
    """
    # 此存根在 DatacloudOutputMiddleware 未注入时提供降级日志
    data_keys: list[str] | None = None
    try:
        normalized = _normalize_emit_result_data(data)
        data_keys = list(normalized.keys()) if normalized else None
    except (TypeError, ValueError):
        data_keys = None
    logger.info(
        "emit_result (stub): result_type=%s answer=%r data_keys=%s file_path=%s",
        result_type,
        answer[:100] if answer else "",
        data_keys,
        file_path,
    )
    return "result_emitted"

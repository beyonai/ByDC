"""
DataCloud 输出中间件

提供 emit_result 工具，将结果转换为 6001 协议格式。
"""

from __future__ import annotations
from typing import Any, Optional
import logging
import json

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _make_emit_result_tool(gateway_context: Optional[Any] = None):
    """创建 emit_result 工具（绑定 gateway_context）。"""

    @tool
    def emit_result(
        result_type: str,
        answer: str,
        data: Optional[dict] = None,
        file_path: Optional[str] = None,
    ) -> str:
        """
        输出结构化结果到 6001 协议格式。

        Args:
            result_type: 结果类型
                - "query_result": 查询结果（带数据表格）
                - "csv_file": CSV 文件
                - "json": JSON 数据
                - "text": 纯文本答案
            answer: 文本答案（用户可读的自然语言描述）
            data: 结构化数据（可选）
                - 对于 query_result: {"columns": [...], "rows": [...]}
                - 对于 json: 任意 JSON 对象
            file_path: 文件路径（可选，用于 csv_file 类型）

        Returns:
            输出状态消息
        """
        try:
            output = _build_6001_format(
                result_type=result_type,
                answer=answer,
                data=data,
                file_path=file_path,
            )

            if gateway_context:
                _send_via_gateway(gateway_context, output)
            else:
                logger.info("emit_result output: %s", json.dumps(output, ensure_ascii=False))

            return f"已输出结果: {result_type}"

        except Exception as exc:
            logger.error("emit_result failed: %s", exc)
            return f"输出失败: {exc}"

    return emit_result


def _build_6001_format(
    result_type: str,
    answer: str,
    data: Optional[dict] = None,
    file_path: Optional[str] = None,
) -> dict[str, Any]:
    """构建 6001 协议格式。"""
    output: dict[str, Any] = {
        "type": "result",
        "result_type": result_type,
        "answer": answer,
    }

    if result_type == "query_result" and data:
        output["data"] = {
            "columns": data.get("columns", []),
            "rows": data.get("rows", []),
            "total": len(data.get("rows", [])),
        }
    elif result_type == "json" and data:
        output["data"] = data
    elif result_type == "csv_file" and file_path:
        output["file_path"] = file_path

    return output


def _send_via_gateway(gateway_context: Any, output: dict[str, Any]) -> None:
    """通过 gateway 发送输出（调用 gateway_context.emit_chunk）。

    emit_result 工具为同步函数，而 emit_chunk 为异步方法。
    Agent 执行时必定存在运行中的事件循环（astream_events），通过
    create_task 将 emit_chunk 调用调度进当前循环（fire-and-forget）。
    """
    import asyncio  # noqa: PLC0415

    try:
        emit_chunk = getattr(gateway_context, "emit_chunk", None)
        if emit_chunk is None:
            logger.warning("_send_via_gateway: gateway_context has no emit_chunk method")
            return

        if asyncio.iscoroutinefunction(emit_chunk):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(emit_chunk(output))
            except RuntimeError:
                # 没有运行中的事件循环（单元测试场景），直接跳过
                logger.info(
                    "_send_via_gateway: no running event loop; output=%s",
                    json.dumps(output, ensure_ascii=False, default=str),
                )
        else:
            emit_chunk(output)

    except Exception as exc:
        logger.error("_send_via_gateway failed: %s", exc)


class DatacloudOutputMiddleware(AgentMiddleware):
    """
    DataCloud 输出中间件

    提供 emit_result 工具，将结果转换为 6001 协议格式。
    对应重构方案 §3.1.4.4 自定义 Middleware 1
    """

    def __init__(self, gateway_context: Optional[Any] = None):
        self.gateway_context = gateway_context
        self.tools = [_make_emit_result_tool(gateway_context)]

    # Expose module-level helpers for testing
    _build_6001_format = staticmethod(_build_6001_format)

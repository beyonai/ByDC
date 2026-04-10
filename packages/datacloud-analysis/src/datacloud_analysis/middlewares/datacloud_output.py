"""
DataCloud 输出中间件

提供 emit_result 工具，将结果转换为 6001 协议格式。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


def _normalize_emit_result_data(data: dict | str | None) -> dict | None:
    """将 emit_result 的 data 规范为 dict 或 None（兼容 LLM 传入 JSON 字符串）。

    Args:
        data: 结构化对象、JSON 字符串或省略。

    Returns:
        解析后的 dict，或 ``None``（无数据）。

    Raises:
        ValueError: JSON 非法，或解析结果不是 JSON 对象。
        TypeError: ``data`` 类型既不是 dict、str 也不是 None。
    """

    if data is None:
        return None
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        raw = data.strip()
        if not raw:
            return None
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("data 字符串不是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                f"data JSON 解析后必须是对象（dict），实际为 {type(parsed).__name__}",
            )
        return parsed
    raise TypeError(f"data 必须是 dict、str 或 None，实际为 {type(data).__name__}")


class _EmitResultInput(BaseModel):
    """emit_result 工具的输入模型。

    data 字段接受 JSON 字符串（LLM 标准输出）或 dict（兼容直接调用），
    通过 field_validator 在进入工具前统一规范为字符串，
    彻底避免 Pydantic union 推断歧义导致的 ValidationError。
    """

    result_type: str
    answer: str
    data: str | None = None
    file_path: str | None = None

    @field_validator("data", mode="before")
    @classmethod
    def _coerce_data(cls, v: Any) -> str | None:
        """将 dict 序列化为 JSON 字符串，str/None 原样返回。"""
        if v is None:
            return None
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        return v


def _make_emit_result_tool(gateway_context: Any | None = None):
    """创建 emit_result 工具（绑定 gateway_context）。"""

    def _emit_result(
        result_type: str,
        answer: str,
        data: str | None = None,
        file_path: str | None = None,
    ) -> str:
        try:
            normalized_data = _normalize_emit_result_data(data)
            output = _build_6001_format(
                result_type=result_type,
                answer=answer,
                data=normalized_data,
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

    return StructuredTool.from_function(
        func=_emit_result,
        name="emit_result",
        description=(
            "输出结构化结果到 6001 协议格式。\n\n"
            "Args:\n"
            "    result_type: 结果类型（query_result / csv_file / json / text）\n"
            "    answer: 文本答案（用户可读的自然语言描述）\n"
            "    data: 结构化数据（可选）；传入 JSON 对象字符串\n"
            "        - 对于 query_result: {\"columns\": [...], \"rows\": [...]}\n"
            "        - 对于 json: 任意 JSON 对象\n"
            "    file_path: 文件路径（可选，用于 csv_file 类型）"
        ),
        args_schema=_EmitResultInput,
    )


def _build_6001_format(
    result_type: str,
    answer: str,
    data: dict | None = None,
    file_path: str | None = None,
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
                task = loop.create_task(emit_chunk(output))
                task.add_done_callback(
                    lambda t: (
                        logger.error("_send_via_gateway emit_chunk failed: %s", t.exception())
                        if not t.cancelled() and t.exception() is not None
                        else None
                    )
                )
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

    def __init__(self, gateway_context: Any | None = None):
        self.gateway_context = gateway_context
        self.tools = [_make_emit_result_tool(gateway_context)]

    # Expose module-level helpers for testing
    _build_6001_format = staticmethod(_build_6001_format)

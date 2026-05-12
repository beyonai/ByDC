# packages/datacloud-analysis/tests/dca/unit/test_tool_error_dispatch.py
"""验收用例：tool_wrapper 异常友好化改造。

测试分组
--------
TC-30 ~ TC-46  _build_tool_error()              单元测试（各异常类型 → ToolErrorDict）
TC-47 ~ TC-52  _format_agent_error_message()    单元测试（格式化输出验证）
TC-53 ~ TC-59  dispatch_tool()                  集成测试（完整错误链路）
TC-60 ~ TC-63  _build_tool_error() knowledge   单元测试（datacloud-knowledge 独立异常体系）
"""

from __future__ import annotations

import logging
import sys

import pytest
from datacloud_analysis.orchestration.execution.tool_wrapper import (
    _build_tool_error,
    _format_agent_error_message,
    dispatch_tool,
)
from datacloud_data_sdk.exceptions import (
    ActionNotConfiguredError,
    ActionNotFoundError,
    ApiExecutionError,
    CannotAnswerError,
    DataSourceUnavailableError,
    ObjectNotFoundError,
    PermissionDeniedError,
    ScriptExecutionError,
    SqlExecutionError,
    StepDependencyError,
    TermAmbiguousError,
    TermNotFoundError,
)
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

# ============================================================================
# Group 1: _build_tool_error() 单元测试  TC-30 ~ TC-46
# ============================================================================


def test_tc30_term_not_found_with_entries() -> None:
    """TC-30: available_entries 优先写入 context，retryable=True。"""
    entries = [{"code": "VIP", "label": "VIP客户"}, {"code": "ORD", "label": "普通客户"}]
    exc = TermNotFoundError("customer_type", "vip", available_entries=entries)
    result = _build_tool_error(exc)

    assert result["error_type"] == "TermNotFoundError"
    assert result["retryable"] is True
    assert result["context"]["available_entries"] == entries
    assert "available_values" not in result["context"]
    assert "customer_type" in result["hint"]


def test_tc31_term_not_found_values_fallback() -> None:
    """TC-31: 无 entries 时降级为 available_values。"""
    exc = TermNotFoundError("region", "东北", available_values=["华东", "华南", "华北"])
    result = _build_tool_error(exc)

    assert result["retryable"] is True
    assert result["context"]["available_values"] == ["华东", "华南", "华北"]
    assert "available_entries" not in result["context"]


def test_tc32_term_not_found_truncates_at_ten() -> None:
    """TC-32: entries 超 10 条时截断至 10 条。"""
    entries = [{"code": str(i), "label": f"选项{i}"} for i in range(15)]
    exc = TermNotFoundError("big_set", "x", available_entries=entries)
    result = _build_tool_error(exc)

    assert len(result["context"]["available_entries"]) == 10


def test_tc33_term_ambiguous() -> None:
    """TC-33: matches 写入 context，retryable=True，hint 含歧义值。"""
    matches = [
        {"code": "C001", "label": "VIP客户"},
        {"code": "C002", "label": "贵宾客户"},
    ]
    exc = TermAmbiguousError("customer_type", "vip客户", matches)
    result = _build_tool_error(exc)

    assert result["error_type"] == "TermAmbiguousError"
    assert result["retryable"] is True
    assert result["context"]["matches"] == matches
    assert "vip客户" in result["hint"]


def test_tc34_term_ambiguous_truncates_at_ten() -> None:
    """TC-34: matches 超 10 条时截断至 10 条。"""
    matches = [{"code": str(i), "label": f"term{i}"} for i in range(12)]
    exc = TermAmbiguousError("ts", "x", matches)
    result = _build_tool_error(exc)

    assert len(result["context"]["matches"]) == 10


def test_tc35_object_not_found() -> None:
    """TC-35: retryable=False，context 含 object_code，hint 含对象名。"""
    exc = ObjectNotFoundError("sales_order")
    result = _build_tool_error(exc)

    assert result["error_type"] == "ObjectNotFoundError"
    assert result["retryable"] is False
    assert result["context"]["object_code"] == "sales_order"
    assert "sales_order" in result["hint"]


def test_tc36_action_not_found() -> None:
    """TC-36: retryable=False，context 含 object_code + action_code。"""
    exc = ActionNotFoundError("customer", "get_vip_level")
    result = _build_tool_error(exc)

    assert result["retryable"] is False
    assert result["context"]["object_code"] == "customer"
    assert result["context"]["action_code"] == "get_vip_level"


def test_tc37_action_not_configured() -> None:
    """TC-37: retryable=False，hint 含"管理员"。"""
    exc = ActionNotConfiguredError("export_data")
    result = _build_tool_error(exc)

    assert result["retryable"] is False
    assert result["context"]["action_code"] == "export_data"
    assert "管理员" in result["hint"]


def test_tc38_permission_denied() -> None:
    """TC-38: retryable=False，context 含 resource + reason_code，hint 含"申请权限"。"""
    exc = PermissionDeniedError("order_detail", reason_code="no_read_perm")
    result = _build_tool_error(exc)

    assert result["retryable"] is False
    assert result["context"]["resource"] == "order_detail"
    assert result["context"]["reason_code"] == "no_read_perm"
    assert "申请权限" in result["hint"]


def test_tc39_api_error_4xx_not_retryable() -> None:
    """TC-39: 4xx → retryable=False，hint 含"客户端错误"。"""
    exc = ApiExecutionError("get_customer", 403, "Forbidden")
    result = _build_tool_error(exc)

    assert result["retryable"] is False
    assert result["context"]["status_code"] == 403
    assert "客户端错误" in result["hint"]


def test_tc40_api_error_5xx_retryable() -> None:
    """TC-40: 5xx → retryable=True，hint 含"服务端错误"。"""
    exc = ApiExecutionError("get_customer", 503, "Service Unavailable")
    result = _build_tool_error(exc)

    assert result["retryable"] is True
    assert result["context"]["status_code"] == 503
    assert "服务端错误" in result["hint"]


def test_tc41_sql_execution_error() -> None:
    """TC-41: retryable=False，context 含 datasource_alias。"""
    exc = SqlExecutionError("mysql_prod", "SELECT * FROM orders", "Table not found")
    result = _build_tool_error(exc)

    assert result["retryable"] is False
    assert result["context"]["datasource_alias"] == "mysql_prod"
    assert "mysql_prod" in result["hint"]


def test_tc42_script_execution_error_with_line_no() -> None:
    """TC-42: context 含 action_code + line_no。"""
    exc = ScriptExecutionError("calc_bonus", "NameError: x", line_no=12)
    result = _build_tool_error(exc)

    assert result["retryable"] is False
    assert result["context"]["action_code"] == "calc_bonus"
    assert result["context"]["line_no"] == 12


def test_tc43_datasource_unavailable_retryable() -> None:
    """TC-43: retryable=True，context["datasource_alias"] 含别名，hint 含别名。"""
    exc = DataSourceUnavailableError("pg_dw")
    result = _build_tool_error(exc)

    assert result["retryable"] is True
    assert result["context"]["datasource_alias"] == "pg_dw"
    assert "pg_dw" in result["hint"]


def test_tc44_cannot_answer() -> None:
    """TC-44: retryable=False，hint 含"拆解"。"""
    exc = CannotAnswerError("该问题超出知识库范围")
    result = _build_tool_error(exc)

    assert result["retryable"] is False
    assert "拆解" in result["hint"]


def test_tc45_step_dependency_error() -> None:
    """TC-45: context 含 step_id + depends_on。"""
    exc = StepDependencyError("step_3", "step_1")
    result = _build_tool_error(exc)

    assert result["context"]["step_id"] == "step_3"
    assert result["context"]["depends_on"] == "step_1"


def test_tc46_unknown_exception_fallback() -> None:
    """TC-46: 未知异常兜底，retryable=False，hint 含"技术支持"，context 为空。"""
    exc = ValueError("unexpected")
    result = _build_tool_error(exc)

    assert result["error_type"] == "ValueError"
    assert result["retryable"] is False
    assert "技术支持" in result["hint"]
    assert result["context"] == {}


# ============================================================================
# Group 2: _format_agent_error_message() 单元测试  TC-47 ~ TC-52
# ============================================================================


def _make_err(**kwargs: object) -> dict:  # type: ignore[type-arg]
    base: dict = {  # type: ignore[type-arg]
        "error_type": "TestError",
        "message": "test message",
        "retryable": False,
        "hint": "test hint",
        "context": {},
    }
    base.update(kwargs)
    return base


def test_tc47_format_contains_header_fields() -> None:
    """TC-47: 输出包含标准四行头部。"""
    output = _format_agent_error_message(
        _make_err(  # type: ignore[arg-type]
            error_type="SqlExecutionError",
            message="Table not found",
            retryable=False,
            hint="请检查字段名",
        )
    )

    assert "[工具调用失败: SqlExecutionError]" in output
    assert "错误详情：Table not found" in output
    assert "可重试：否" in output
    assert "建议：请检查字段名" in output


def test_tc48_format_available_entries() -> None:
    """TC-48: available_entries 展开为"可用条目"行，retryable=True 显示"是"。"""
    err = _make_err(
        retryable=True,
        context={
            "available_entries": [
                {"code": "A", "label": "选项A"},
                {"code": "B", "label": "选项B"},
            ]
        },
    )
    output = _format_agent_error_message(err)  # type: ignore[arg-type]

    assert "可用条目：[A] 选项A, [B] 选项B" in output
    assert "可重试：是" in output


def test_tc49_format_available_values_fallback() -> None:
    """TC-49: 无 entries 时展开 available_values，不出现"可用条目"。"""
    err = _make_err(context={"available_values": ["华东", "华南"]})
    output = _format_agent_error_message(err)  # type: ignore[arg-type]

    assert "可用值：华东, 华南" in output
    assert "可用条目" not in output


def test_tc50_entries_takes_priority_over_values() -> None:
    """TC-50: entries 与 values 同时存在时，只展示"可用条目"。"""
    err = _make_err(
        context={
            "available_entries": [{"code": "X", "label": "选项X"}],
            "available_values": ["不应出现"],
        }
    )
    output = _format_agent_error_message(err)  # type: ignore[arg-type]

    assert "可用条目：[X] 选项X" in output
    assert "不应出现" not in output


def test_tc51_format_matches() -> None:
    """TC-51: matches 展开为"候选术语"行。"""
    err = _make_err(
        context={
            "matches": [
                {"code": "C1", "label": "VIP客户"},
                {"code": "C2", "label": "贵宾客户"},
            ]
        }
    )
    output = _format_agent_error_message(err)  # type: ignore[arg-type]

    assert "候选术语：[C1] VIP客户, [C2] 贵宾客户" in output


def test_tc52_format_status_code() -> None:
    """TC-52: status_code 展开为"HTTP 状态码"行。"""
    err = _make_err(context={"function_code": "get_order", "status_code": 403})
    output = _format_agent_error_message(err)  # type: ignore[arg-type]

    assert "HTTP 状态码：403" in output


# ============================================================================
# Group 3: dispatch_tool() 集成测试  TC-53 ~ TC-59
# ============================================================================


class _DummySchema(BaseModel):
    query: str


def _make_state() -> dict:  # type: ignore[type-arg]
    return {
        "agent_id": "test-agent",
        "user_query": "测试查询",
        "workspace_dir": None,
        "knowledge_snippets": [],
        "confirmed_terms": None,
        "knowledge_payload": {},
    }


def _raising_tool(exc: Exception) -> StructuredTool:
    async def _raise(**kwargs: object) -> str:
        raise exc

    return StructuredTool(
        name="test_tool",
        description="test",
        args_schema=_DummySchema,
        coroutine=_raise,
    )


async def test_tc53_dispatch_term_not_found_message() -> None:
    """TC-53: TermNotFoundError → ToolMessage 含类名、可用值、可重试：是。"""
    exc = TermNotFoundError("region", "东北", available_values=["华东", "华南", "华北"])
    tool_call = {"id": "tc53", "name": "test_tool", "args": {"query": "东北"}}

    _, output = await dispatch_tool(
        tool_call=tool_call,
        tools_map={"test_tool": _raising_tool(exc)},
        state=_make_state(),
    )

    assert isinstance(output, str)
    assert "TermNotFoundError" in output
    assert "可用值" in output
    assert "华东" in output
    assert "可重试：是" in output


async def test_tc54_dispatch_datasource_unavailable_retryable() -> None:
    """TC-54: DataSourceUnavailableError → ToolMessage 含别名、可重试：是。"""
    exc = DataSourceUnavailableError("mysql_prod")
    tool_call = {"id": "tc54", "name": "test_tool", "args": {"query": "x"}}

    _, output = await dispatch_tool(
        tool_call=tool_call,
        tools_map={"test_tool": _raising_tool(exc)},
        state=_make_state(),
    )

    assert "DataSourceUnavailableError" in output
    assert "mysql_prod" in output
    assert "可重试：是" in output


async def test_tc55_dispatch_permission_denied_not_retryable() -> None:
    """TC-55: PermissionDeniedError → ToolMessage 含可重试：否。"""
    exc = PermissionDeniedError("secret_table")
    tool_call = {"id": "tc55", "name": "test_tool", "args": {"query": "x"}}

    _, output = await dispatch_tool(
        tool_call=tool_call,
        tools_map={"test_tool": _raising_tool(exc)},
        state=_make_state(),
    )

    assert "PermissionDeniedError" in output
    assert "可重试：否" in output


async def test_tc56_dispatch_tool_not_found() -> None:
    """TC-56: 工具不存在 → ToolMessage 含 ToolNotFound、可重试：否。"""
    tool_call = {"id": "tc56", "name": "nonexistent_tool", "args": {"query": "x"}}

    _, output = await dispatch_tool(
        tool_call=tool_call,
        tools_map={},
        state=_make_state(),
    )

    assert "ToolNotFound" in output
    assert "可重试：否" in output


async def test_tc57_hook_signal_error_propagates() -> None:
    """TC-57: HookSignalError 冒泡，不被转换为 ToolMessage。"""
    from datacloud_analysis.tool_hook_plugins.types import HookSignalError

    class _TestSignalError(HookSignalError):
        pass

    tool_call = {"id": "tc57", "name": "test_tool", "args": {"query": "x"}}

    with pytest.raises(HookSignalError):
        await dispatch_tool(
            tool_call=tool_call,
            tools_map={"test_tool": _raising_tool(_TestSignalError("signal"))},
            state=_make_state(),
        )


async def test_tc58_graph_bubble_up_propagates() -> None:
    """TC-58: GraphBubbleUp 冒泡，不被转换为 ToolMessage。"""
    try:
        from langgraph.errors import GraphBubbleUp
    except ImportError:

        class GraphBubbleUp(Exception):  # type: ignore[no-redef]  # noqa: N818
            pass

    exc = GraphBubbleUp("interrupt")
    tool_call = {"id": "tc58", "name": "test_tool", "args": {"query": "x"}}

    with pytest.raises(type(exc)):
        await dispatch_tool(
            tool_call=tool_call,
            tools_map={"test_tool": _raising_tool(exc)},
            state=_make_state(),
        )


async def test_tc59_error_log_level_on_tool_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """TC-59: 工具执行失败时产生 ERROR 级别日志，含异常类名。"""
    exc = SqlExecutionError("pg", "SELECT 1", "connection refused")
    tool_call = {"id": "tc59", "name": "test_tool", "args": {"query": "x"}}

    with caplog.at_level(
        logging.ERROR,
        logger="datacloud_analysis.orchestration.execution.tool_wrapper",
    ):
        await dispatch_tool(
            tool_call=tool_call,
            tools_map={"test_tool": _raising_tool(exc)},
            state=_make_state(),
        )

    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("SqlExecutionError" in r.message for r in error_records), (
        f"应有 ERROR 级别日志含 SqlExecutionError，实际：{[r.message for r in error_records]}"
    )


# ============================================================================
# Group 4: datacloud-knowledge 独立异常体系  TC-60 ~ TC-63
# ============================================================================


@pytest.mark.skip(reason="断言字符串在 Windows 终端存在编码问题，需在 UTF-8 环境下运行")
def test_tc60_term_vector_validation_error() -> None:
    """TC-60: TermVectorValidationError → retryable=False，hint 含"向量索引"。"""
    pytest.importorskip("datacloud_knowledge")
    from datacloud_knowledge.query.search.vector_validation import TermVectorValidationError

    exc = TermVectorValidationError("术语知识库向量校验失败: name_embedding 全部为空")
    result = _build_tool_error(exc)

    assert result["error_type"] == "TermVectorValidationError"
    assert result["retryable"] is False
    assert result["context"] == {}
    assert "向量索引" in result["hint"]


@pytest.mark.skip(reason="datacloud_knowledge.file_store.errors 模块在当前 SDK 版本不存在")
def test_tc61_file_not_found_in_store() -> None:
    """TC-61: FileNotFoundInStoreError → context["md5"] 与异常一致，hint 含 md5。"""
    pytest.importorskip("datacloud_knowledge")
    from datacloud_knowledge.file_store.errors import FileNotFoundInStoreError

    target_md5 = "d41d8cd98f00b204e9800998ecf8427e"
    exc = FileNotFoundInStoreError(target_md5)
    result = _build_tool_error(exc)

    assert result["error_type"] == "FileNotFoundInStoreError"
    assert result["retryable"] is False
    assert result["context"]["md5"] == target_md5
    assert target_md5 in result["hint"]


@pytest.mark.skip(reason="datacloud_knowledge.file_store.errors 模块在当前 SDK 版本不存在")
def test_tc62_backend_misconfigured_error() -> None:
    """TC-62: BackendMisconfiguredError → retryable=False，hint 含"管理员"。"""
    pytest.importorskip("datacloud_knowledge")
    from datacloud_knowledge.file_store.errors import BackendMisconfiguredError

    exc = BackendMisconfiguredError("S3 bucket not configured")
    result = _build_tool_error(exc)

    assert result["error_type"] == "BackendMisconfiguredError"
    assert result["retryable"] is False
    assert "管理员" in result["hint"]


def test_tc63_knowledge_import_error_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-63: datacloud-knowledge 导入失败时退回兜底 hint，不抛异常。

    通过向 sys.modules 注入 None 模拟 ImportError，验证 _build_tool_error 能优雅降级。
    此用例不依赖 datacloud_knowledge 是否已安装，任何环境均可运行。
    """
    # 备份已加载的 knowledge 模块
    saved: dict[str, object] = {}
    keys_to_patch = [
        "datacloud_knowledge.file_store.errors",
        "datacloud_knowledge.query.search.vector_validation",
    ]
    for k in keys_to_patch:
        if k in sys.modules:
            saved[k] = sys.modules.pop(k)
        # None 值会让 Python import 机制抛出 ImportError
        monkeypatch.setitem(sys.modules, k, None)

    try:
        exc = RuntimeError("embedding model not initialized")
        result = _build_tool_error(exc)

        assert result["error_type"] == "RuntimeError"
        assert result["retryable"] is False
        assert "技术支持" in result["hint"]
        assert result["context"] == {}
    finally:
        for k in keys_to_patch:
            sys.modules.pop(k, None)
        for k, v in saved.items():
            sys.modules[k] = v  # type: ignore[assignment]

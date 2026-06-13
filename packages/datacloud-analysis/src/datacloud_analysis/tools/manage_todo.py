"""manage_todo 工具 — 任务分解与进度追踪（附02 4.5节 + 附05 3.3节）。

LLM 通过此工具自主管理当前任务分解列表，防止多步推理中遗忘原始目标。

设计原则（对应 Hermes-Agent 的 TodoStore 机制）：
  - 读写两用：提供 todos 则写入，不提供则读取
  - merge=True 时按 id 更新，False 时全量替换
  - 只有 pending/in_progress 的项会注入 dynamic_prompt（completed/cancelled 不注入）
  - 数据存在 AgentState.todos（已有字段，checkpoint 安全）
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

# todo 的合法状态
_VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}


@tool("manage_todo")
def manage_todo(
    todos: list[dict[str, Any]] | None = None,
    merge: bool = False,
) -> str:
    """管理当前任务分解列表。复杂的多步骤任务（3步以上）时使用。

    **写入**：提供 todos 数组，每项包含 {id, content, status}
      status 可选值：pending / in_progress / completed / cancelled
      列表顺序即优先级，一次只能一个 in_progress。
      merge=False（默认）：全量替换列表
      merge=True：按 id 更新或新增项

    **读取**：不提供 todos，返回当前列表状态。

    使用时机：
      - 任务开始：分解任务步骤，全部设为 pending
      - 开始某步：将该步状态改为 in_progress
      - 完成某步：立即标记为 completed
      - 某步失败：标记为 cancelled，创建新的修订步骤

    Args:
        todos: 任务项列表（写入）或 None（读取）。
        merge: True=按 id 更新，False=全量替换（默认）。
    """
    # manage_todo 的实际写入通过 state 注入实现
    # 此处作为工具的 schema 定义，实际执行逻辑由 make_manage_todo_tool 工厂函数注入
    return "manage_todo 工具已注册，请通过 make_manage_todo_tool() 工厂函数使用"


def make_manage_todo_tool(
    get_state_fn: Any,
) -> Any:
    """工厂函数，通过闭包注入 state 读写能力。

    Args:
        get_state_fn: 返回当前 AgentState dict 的函数（闭包，per-request）。

    Returns:
        带 state 写入能力的 manage_todo LangChain tool 对象。
    """

    @tool("manage_todo")
    def _manage_todo(
        todos: list[dict[str, Any]] | None = None,
        merge: bool = False,
    ) -> str:
        """管理当前任务分解列表。复杂的多步骤任务（3步以上）时使用。

        写入：提供 todos 数组，每项包含 {id, content, status}
          status 可选值：pending / in_progress / completed / cancelled
          列表顺序即优先级，一次只能一个 in_progress。

        读取：不提供 todos，返回当前列表状态。
        """
        state = get_state_fn() or {}
        current: list[dict[str, Any]] = list(state.get("todos") or [])

        if todos is None:
            # 读取模式
            return _format_todo_list(current)

        # 写入模式
        validated = [_validate_item(t) for t in todos]

        if merge:
            # 按 id 合并：存在则更新，不存在则追加
            current_by_id = {t.get("id", ""): t for t in current}
            for item in validated:
                item_id = item.get("id", "")
                if item_id and item_id in current_by_id:
                    current_by_id[item_id].update(item)
                else:
                    current.append(item)
                    if item_id:
                        current_by_id[item_id] = item
            new_todos = list(current_by_id.values()) if current_by_id else current
        else:
            # 全量替换
            new_todos = validated

        # 写回 state
        state["todos"] = new_todos

        summary = _build_summary(new_todos)
        return f"任务列表已更新：{summary}"

    return _manage_todo


def _validate_item(item: dict[str, Any]) -> dict[str, Any]:
    """规范化单个 todo 项。"""
    status = str(item.get("status", "pending")).strip()
    if status not in _VALID_STATUSES:
        status = "pending"
    return {
        "id":      str(item.get("id", "")).strip(),
        "content": str(item.get("content", "")).strip(),
        "status":  status,
    }


def _format_todo_list(todos: list[dict[str, Any]]) -> str:
    """格式化 todo 列表为可读文本。"""
    if not todos:
        return "任务列表为空"
    status_mark = {"in_progress": "[>]", "pending": "[ ]", "completed": "[x]", "cancelled": "[~]"}
    lines = ["当前任务列表："]
    for i, t in enumerate(todos, 1):
        mark = status_mark.get(t.get("status", ""), "[ ]")
        lines.append(f"  {mark} {i}. {t.get('content', '')}（id={t.get('id', '')}）")
    return "\n".join(lines)


def _build_summary(todos: list[dict[str, Any]]) -> str:
    """构建状态摘要。"""
    counts: dict[str, int] = {}
    for t in todos:
        s = t.get("status", "pending")
        counts[s] = counts.get(s, 0) + 1
    parts = [f"{v}个{k}" for k, v in counts.items()]
    return "，".join(parts) if parts else "无"

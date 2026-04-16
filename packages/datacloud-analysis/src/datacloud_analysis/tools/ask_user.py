from __future__ import annotations

from langchain_core.tools import tool
from langgraph.types import interrupt


@tool("ask_user")
async def ask_user(question: str, reason: str = "") -> str:
    """向用户提问，等待用户作答后 ReAct 恢复。

    工具调用后图立即挂起（checkpoint 已写入），
    worker 层检测到 snapshot.interrupts 后通过网关推送问题给前端。
    ResumeCommand 到达后，本工具返回用户的回答字符串。

    Args:
        question: 向用户提出的问题
        reason: 为何需要询问用户（用于审计日志）
    """
    answer = interrupt(
        {
            "question": question,
            "reason": reason,
            "reason_code": "ASK_USER",
        }
    )
    return str(answer)

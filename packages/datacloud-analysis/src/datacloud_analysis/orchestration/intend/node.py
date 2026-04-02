from __future__ import annotations
from typing import Any
from langchain_core.runnables import RunnableConfig
from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.orchestration.intend.command_router import CommandRouter
from datacloud_analysis.orchestration.intend.intent_classifier import IntentClassifier

_router = CommandRouter()
_classifier = IntentClassifier()

async def intend_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    gw_ctx = (config.get("configurable") or {}).get("gateway_context")
    messages = state.get("messages") or []
    user_query = ""
    if messages:
        last = messages[-1]
        user_query = last.content if hasattr(last, "content") else str(last)

    # 1. 命令路由
    result = await _router.try_dispatch(
        user_query=user_query,
        state=state,
        config=config,
        gateway_context=gw_ctx,
    )
    if result["handled"]:
        return {
            "intent": "command",
            "intent_source": "command",
            "command_result": result["payload"],
            "execution_status": "command_done",
            "user_query": user_query,
        }

    # 2. LLM 意图分类
    intent = await _classifier.classify(user_query, state)
    return {
        "intent": intent,
        "intent_source": intent,
        "execution_status": "execution",
        "user_query": user_query,
    }

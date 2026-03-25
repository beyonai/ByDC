"""② Dynamic DAG generation (design §3.1 DAG_PLAN).

Responsibilities
----------------
- Parse the clear intent and decompose it into a sequence of sub-tasks.
- Store the plan in the graph state.
"""

from __future__ import annotations

import logging
import json
from typing import cast

from langchain_core.messages import SystemMessage, HumanMessage
from langchain.chat_models import init_chat_model
import os

from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


async def dag_node(state: AgentState) -> dict:
    """Generate the execution DAG/plan from the parsed intent.

    Input state keys:
        intent: The clear, rewritten intent.
        
    Output state updates:
        plan: List of sub-task dicts.
    """
    logger.debug("dag_node: generating execution DAG …")
    
    intent = state.get("intent", "")
    
    model = os.getenv("DATACLOUD_LLM_REASONING_MODEL", "openai:Qwen/Qwen3-235B-A22B")
    if not model.startswith("openai:"):
        model = f"openai:{model}"
        
    llm = init_chat_model(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DATACLOUD_LLM_REASONING_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DATACLOUD_LLM_REASONING_API_BASE"),
    )

    sys_prompt = f"""你是一个任务规划专家。
需要分析的目标：{intent}

请将其拆解为一个个具体的数据查询或代码执行子任务。
如果是单次数据查询即可解答的，就只输出一个子任务。

返回格式必须为严格的 JSON 数组，每个元素包含：
- "id": "任务ID (如 t1)"
- "type": "工具类型 (如 data_query)"
- "description": "任务描述，具体查什么数据"
- "status": "pending"
- "deps": ["依赖的前置任务ID列表"]

示例输出：
[
    {{
        "id": "t1",
        "type": "data_query",
        "description": "查询近30天未推进的商机列表",
        "status": "pending",
        "deps": []
    }}
]
"""

    response = await llm.ainvoke([SystemMessage(content=sys_prompt)])
    
    try:
        content = cast(str, response.content)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        plan = json.loads(content)
        if not isinstance(plan, list):
            plan = []
    except Exception as e:
        logger.warning("Failed to parse DAG JSON, fallback to single step. Error: %s", e)
        plan = [{
            "id": "t1",
            "type": "data_query",
            "description": intent,
            "status": "pending",
            "deps": []
        }]

    return {"plan": plan}

"""② Dynamic DAG generation (design §3.1 DAG_PLAN).

Responsibilities
----------------
- Parse the clear intent and decompose it into a sequence of sub-tasks.
- Store the plan in the graph state.
- Emit a REASONING_LOG_DELTA thinking event with the task breakdown.
"""

from __future__ import annotations

import json
import logging
import os
from typing import cast

from gateway_sdk import EventType, StreamChunkEvent
from gateway_sdk.core.protocol.content_type import SseReasonMessageType
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage

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

请将其拆解为一个个具体的子任务。如果单次数据查询即可解答，只输出一个子任务。

## 支持的任务类型

| type | 使用场景 |
|------|---------|
| data_query | 向外部数据服务查询原始数据，description 为自然语言问题 |
| code_exec | 对已查询到的数据文件进行计算/统计/关联分析，必须有 deps，须在 params.code 中提供 Python 代码 |
| search_knowledge | 检索知识库 |
| render_report | 生成报告 |

## 判断规则（重要）

- 任务需要"从系统查询/获取数据" → 使用 data_query，deps 可为空
- 任务是"基于已查结果进行统计/汇总/计算/关联"且有前置任务 → 必须使用 code_exec，不得使用 data_query
- deps 为空的任务禁止使用 code_exec

## code_exec 的 Python 代码约定

- 变量 `input_files` 已注入，类型为 dict，key = 前置任务 id，value = JSONL 文件绝对路径
- JSONL 格式：第一行是 meta（含 columns、total 字段），后续每行是一条数据记录
- 可直接使用 `pandas`（as pd）和 `json` 模块，无需 import（已预置）
- 将最终计算结果赋值给 `_result` 变量（类型为 list[dict] 或 dict）
- 同时用 print() 输出关键结果摘要

## 返回格式

返回严格的 JSON 数组，每个元素包含：
- "id": 任务ID（如 t1、t2）
- "type": 任务类型
- "description": 任务描述
- "status": "pending"
- "deps": 依赖的前置任务ID列表
- "params": （仅 code_exec 需要）包含 "code" 字段的对象

## 示例

### 示例1：单次查询
```json
[
    {{
        "id": "t1",
        "type": "data_query",
        "description": "查询近30天未推进的商机列表",
        "status": "pending",
        "deps": []
    }}
]
```

### 示例2：查询后计算（正确示范）
```json
[
    {{
        "id": "t1",
        "type": "data_query",
        "description": "查询企业清单（含网格ID、纳税额字段）",
        "status": "pending",
        "deps": []
    }},
    {{
        "id": "t2",
        "type": "data_query",
        "description": "查询网格清单（含网格ID、网格名称字段）",
        "status": "pending",
        "deps": []
    }},
    {{
        "id": "t3",
        "type": "code_exec",
        "description": "统计各网格的企业数和纳税总额",
        "status": "pending",
        "deps": ["t1", "t2"],
        "params": {{
            "code": "def read_jsonl(path):\\n    rows = []\\n    with open(path, encoding='utf-8') as f:\\n        lines = f.readlines()\\n    for line in lines[1:]:  # 跳过 meta 行\\n        line = line.strip()\\n        if line:\\n            rows.append(json.loads(line))\\n    return pd.DataFrame(rows)\\n\\ndf_corp = read_jsonl(input_files['t1'])\\ndf_grid = read_jsonl(input_files['t2'])\\n\\nmerged = df_corp.merge(df_grid, on='grid_id', how='left')\\nresult = merged.groupby('grid_name').agg(\\n    企业数=('corp_id', 'count'),\\n    纳税总额=('tax_amount', 'sum')\\n).reset_index()\\n\\n_result = result.to_dict('records')\\nprint(result.to_string(index=False))"
        }}
    }}
]
```
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

    # 向前端推送思考消息
    context = state.get("gateway_context")
    if context is not None:
        task_lines = "\n".join(
            f"■ {t['id']}（{t.get('type', 'unknown')}）：{t.get('description', '')}"
            for t in plan
        )
        thinking = f"已将问题拆解为 {len(plan)} 个子任务：\n{task_lines}"

        # 推送思考标题
        await context.emit_chunk(
            StreamChunkEvent(content="任务规划"),
            event_type=EventType.REASONING_LOG_DELTA.value,
            content_type=SseReasonMessageType.think_title.value,
        )
        # 推送思考文本
        await context.emit_chunk(
            StreamChunkEvent(content=thinking),
            event_type=EventType.REASONING_LOG_DELTA.value,
            content_type=SseReasonMessageType.think_text.value,
        )

    return {"plan": plan}

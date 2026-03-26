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


async def dag_node(
    state: AgentState,
    default_prompts: dict | None = None,
    default_tools: dict | None = None,
) -> dict:
    """Generate the execution DAG/plan from the parsed intent.

    Input state keys:
        intent: The clear, rewritten intent.
        
    Output state updates:
        plan: List of sub-task dicts.
    """
    logger.debug("dag_node: generating execution DAG …")
    
    intent = state.get("intent", "")
    prompts_overwrite = state.get("prompts_overwrite") or default_prompts or {}
    dynamic_tools = state.get("dynamic_tools") or default_tools or {}
    custom_tools_hint = ""
    if dynamic_tools:
        custom_tools_hint = (
            "\n## 可用动态工具（来自 Agent 配置）\n"
            f"{', '.join(sorted(dynamic_tools.keys()))}\n"
            "如需要使用，请把任务 type 设置为对应工具名，参数放在 params 中。"
        )
    
    model = os.getenv("DATACLOUD_LLM_REASONING_MODEL", "openai:Qwen/Qwen3-235B-A22B")
    if not model.startswith("openai:"):
        model = f"openai:{model}"
        
    llm = init_chat_model(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DATACLOUD_LLM_REASONING_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DATACLOUD_LLM_REASONING_API_BASE"),
    )

    sys_prompt = prompts_overwrite.get(
        "dag_prompt",
        f"""你是一个任务规划专家。
需要分析的目标：{intent}

请将其拆解为一个个具体的子任务。如果单次数据查询即可解答，只输出一个子任务。

## 支持的任务类型

| type | 使用场景 |
|------|---------|
| [来自【可用动态工具】的项] | 向挂载的外部服务查询原始数据，将其本身作为 type 名并根据工具要求在 params 中提供请求参数 |
| code_exec | 对已查询到的数据文件进行计算/统计/关联分析，必须有 deps，须在 params.code 中提供 Python 代码 |
| search_knowledge | 检索知识库 |
| render_report | 生成报告 |

## 判断规则（重要）

- 任务需要"从系统查询/获取数据" → 必须从下方的【可用动态工具】列表中挑选动作作为 type，deps 可为空
- 任务是"基于已查结果进行统计/汇总/计算/关联"且有前置任务 → 必须使用 code_exec，不得使用查询工具
- deps 为空的任务禁止使用 code_exec
- 对于任何 `*_query` 类型任务，`params` 里必须包含 `query`（或 `question`），禁止返回空 `params`

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
- "params": 执行所需的参数对象（如 code_exec 需要 code，各类 query 需要请求筛选过滤条件等）

## 示例

### 示例1：单次查询
```json
[
    {{
        "id": "t1",
        "type": "analysis_report_query",
        "description": "查询近30天未推进的商机列表",
        "status": "pending",
        "deps": [],
        "params": {{ "status": "未推进" }}
    }}
]
```

### 示例2：查询后计算（正确示范）
```json
[
    {{
        "id": "t1",
        "type": "enterprise_info_query",
        "description": "查询企业清单（含网格ID、纳税额字段）",
        "status": "pending",
        "deps": [],
        "params": {{}}
    }},
    {{
        "id": "t2",
        "type": "grid_list_query",
        "description": "查询网格清单（含网格ID、网格名称字段）",
        "status": "pending",
        "deps": [],
        "params": {{}}
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
{custom_tools_hint}
""",
    )

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
        plan = _normalize_query_params(plan, intent=intent)
    except Exception as e:
        logger.warning("Failed to parse DAG JSON, fallback to single step. Error: %s", e)
        if dynamic_tools:
            fallback_tool = sorted(dynamic_tools.keys())[0]
            plan = [{
                "id": "t1",
                "type": fallback_tool,
                "description": intent,
                "status": "pending",
                "deps": [],
                "params": {"query": intent},
            }]
        else:
            # 在未注入任何动态查询工具时进入澄清分支，避免生成不可执行任务类型。
            return {
                "plan": [],
                "clarify_needed": True,
                "intent": "当前未配置可用的数据查询工具，请先完成 Agent 资源挂载。",
            }
    plan = _normalize_query_params(plan, intent=intent)

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


def _normalize_query_params(
    plan: list[dict[str, object]],
    intent: str,
) -> list[dict[str, object]]:
    """Ensure query tasks always carry a non-empty query/question param."""
    normalized: list[dict[str, object]] = []
    for task in plan:
        if not isinstance(task, dict):
            continue

        task_type = str(task.get("type", ""))
        params_raw = task.get("params", {})
        params = dict(params_raw) if isinstance(params_raw, dict) else {}
        description = str(task.get("description", "") or "")
        fallback_text = description or intent

        if task_type.endswith("_query"):
            if not params.get("query") and not params.get("question"):
                params["query"] = fallback_text
                logger.warning(
                    "dag_node normalized query params: task_id=%s task_type=%s query=%s",
                    task.get("id"),
                    task_type,
                    fallback_text,
                )

        normalized.append({**task, "params": params})

    return normalized

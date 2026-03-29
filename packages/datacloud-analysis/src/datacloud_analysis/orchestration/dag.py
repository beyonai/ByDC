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
from typing import Any, cast

from by_framework import EventType, StreamChunkEvent
from by_framework.core.protocol.content_type import SseReasonMessageType
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)

# 不在 DAG 中规划的任务类型（知识检索在 intent 节点完成，避免与数据子任务混淆）
_DAG_EXCLUDED_PLANNING_TOOLS: frozenset[str] = frozenset({"search_knowledge"})


def _planning_tools_view(dynamic_tools: dict[str, object]) -> dict[str, object]:
    """Subset of dynamic tools the DAG planner may reference as task ``type`` names."""
    return {k: v for k, v in dynamic_tools.items() if k not in _DAG_EXCLUDED_PLANNING_TOOLS}


def _strip_excluded_tasks_from_plan(
    plan: list[dict[str, object]],
    excluded_types: frozenset[str],
) -> list[dict[str, object]]:
    """Drop tasks whose ``type`` is excluded; prune ``deps`` to remaining task ids."""
    kept: list[dict[str, object]] = []
    for task in plan:
        if not isinstance(task, dict):
            continue
        if str(task.get("type", "")) in excluded_types:
            logger.info(
                "dag_node: dropped excluded task type from plan: id=%s type=%s",
                task.get("id"),
                task.get("type"),
            )
            continue
        kept.append(dict(task))
    kept_ids = {str(t.get("id", "")) for t in kept if t.get("id") is not None}
    repaired: list[dict[str, object]] = []
    for task in kept:
        deps = task.get("deps", [])
        if isinstance(deps, list):
            task["deps"] = [d for d in deps if str(d) in kept_ids]
        repaired.append(task)
    return repaired


# 可在 DAG JSON 中出现、由 sandbox_executor 内置调度的 type（不在 planning_tools 里）
_SANDBOX_BUILTIN_PLAN_TYPES: frozenset[str] = frozenset(
    {
        "build_skill",
        "code_exec",
        "file_read",
        "file_write",
        "recall_memory",
        "render_report",
    }
)


def _log_planned_types_vs_registered_tools(
    plan: list[dict[str, object]],
    planning_tools: dict[str, object],
    full_dynamic_tools: dict[str, object],
) -> None:
    """Emit logs to compare model-planned ``type`` vs registered tool keys (debug name mismatches)."""
    planner_keys = sorted(planning_tools.keys())
    full_keys = sorted(full_dynamic_tools.keys())
    only_in_runtime = sorted(set(full_keys) - set(planner_keys))

    logger.info(
        "dag_node: state['dynamic_tools'] keys (count=%d, used at loop execution): %s",
        len(full_keys),
        full_keys,
    )
    logger.info(
        "dag_node: keys shown to DAG planner in HumanMessage (count=%d): %s",
        len(planner_keys),
        planner_keys,
    )
    if only_in_runtime:
        logger.info(
            "dag_node: keys present at execution but hidden from planner prompt: %s",
            only_in_runtime,
        )

    planned_types: list[str] = []
    for t in plan:
        if isinstance(t, dict):
            planned_types.append(str(t.get("type", "")))
    logger.info(
        "dag_node: planned task types from model (count=%d, order preserved): %s",
        len(planned_types),
        planned_types,
    )

    allowed = set(planning_tools.keys()) | set(_SANDBOX_BUILTIN_PLAN_TYPES)
    for t in plan:
        if not isinstance(t, dict):
            continue
        tid = t.get("id", "?")
        ttype = str(t.get("type", ""))
        if not ttype:
            logger.warning("dag_node: task %s has empty type", tid)
            continue
        if ttype in allowed:
            continue
        logger.warning(
            "dag_node: TYPE MISMATCH — task_id=%s model_emitted_type=%r is NOT in "
            "planner_visible_keys and NOT a built-in sandbox type. "
            "planner_visible_keys=%s built_in_types=%s",
            tid,
            ttype,
            planner_keys,
            sorted(_SANDBOX_BUILTIN_PLAN_TYPES),
        )


# ---------------------------------------------------------------------------
# Static system prompt — contains NO variable interpolation.
# Dynamic content (intent, tool list) goes into Layer 3 HumanMessage.
# ---------------------------------------------------------------------------
_DAG_STATIC_SYSTEM = """你是一个任务规划专家。请将分析目标拆解为具体子任务。\
如果单次数据查询即可解答，只输出一个子任务。

## 支持的任务类型

| type | 使用场景 |
|------|---------|
| [来自本轮 HumanMessage 的可用动态工具名] | 向挂载的外部服务查询原始数据，将其本身作为 type 名并根据工具要求在 params 中提供请求参数 |
| code_exec | 对已查询到的数据文件进行计算/统计/关联分析，必须有 deps，须在 params.code 中提供 Python 代码 |
| render_report | 生成报告 |

## 判断规则（重要）

- 问候、寒暄、感谢等与数据分析无关的闲聊：不应由本节点处理（上游应路由为 chitchat）；若仍进入本节点，禁止单独规划仅有 render_report 的任务
- render_report 仅用于在已有查询或 code_exec 结果之后组装最终报告，且不得作为全 plan 中唯一任务，除非前置任务已提供可引用的数据摘要
- 任务需要"从系统查询/获取数据" → 必须从【可用动态工具】列表中挑选动作作为 type，deps 可为空
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
- "params": 执行所需的参数对象

## 示例

### 示例1：单次查询
```json
[
    {
        "id": "t1",
        "type": "analysis_report_query",
        "description": "查询近30天未推进的商机列表",
        "status": "pending",
        "deps": [],
        "params": { "status": "未推进" }
    }
]
```

### 示例2：查询后计算（正确示范）
```json
[
    {
        "id": "t1",
        "type": "enterprise_info_query",
        "description": "查询企业清单（含网格ID、纳税额字段）",
        "status": "pending",
        "deps": [],
        "params": {}
    },
    {
        "id": "t2",
        "type": "grid_list_query",
        "description": "查询网格清单（含网格ID、网格名称字段）",
        "status": "pending",
        "deps": [],
        "params": {}
    },
    {
        "id": "t3",
        "type": "code_exec",
        "description": "统计各网格的企业数和纳税总额",
        "status": "pending",
        "deps": ["t1", "t2"],
        "params": {
            "code": "def read_jsonl(path):\\n    rows = []\\n    with open(path, encoding='utf-8') as f:\\n        lines = f.readlines()\\n    for line in lines[1:]:\\n        line = line.strip()\\n        if line:\\n            rows.append(json.loads(line))\\n    return pd.DataFrame(rows)\\n\\ndf_corp = read_jsonl(input_files['t1'])\\ndf_grid = read_jsonl(input_files['t2'])\\nmerged = df_corp.merge(df_grid, on='grid_id', how='left')\\nresult = merged.groupby('grid_name').agg(企业数=('corp_id','count'),纳税总额=('tax_amount','sum')).reset_index()\\n_result = result.to_dict('records')\\nprint(result.to_string(index=False))"
        }
    }
]
```
"""


async def dag_node(
    state: AgentState,
    gateway_context: Any = None,
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
    planning_tools = _planning_tools_view(dynamic_tools)
    tools_line = ", ".join(sorted(planning_tools.keys())) if planning_tools else "（无动态工具）"

    model = os.getenv("DATACLOUD_LLM_REASONING_MODEL", "openai:Qwen/Qwen3-235B-A22B")
    if not model.startswith("openai:"):
        model = f"openai:{model}"

    llm = init_chat_model(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DATACLOUD_LLM_REASONING_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DATACLOUD_LLM_REASONING_API_BASE"),
    )

    # Layer 0: static system prompt — no variable interpolation, 100% KV-Cache hit.
    # Support legacy key "dag_prompt" for backward compatibility.
    static_sys = prompts_overwrite.get(
        "dag_system_prompt",
        prompts_overwrite.get("dag_prompt", _DAG_STATIC_SYSTEM),
    )

    # Layer 3: dynamic content (intent + tool list) in a single HumanMessage.
    dynamic_human = HumanMessage(
        content=(
            f"【可用动态工具列表】：{tools_line}\n\n"
            f"【需要分析的目标】：{intent}\n\n"
            "请输出 JSON 任务数组。"
        )
    )

    response = await llm.ainvoke(
        [SystemMessage(content=static_sys)]  # Layer 0: static prefix, 100% cache hit
        + [dynamic_human]  # Layer 3: dag node needs no conversation history
    )

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
        plan = _strip_excluded_tasks_from_plan(plan, _DAG_EXCLUDED_PLANNING_TOOLS)
        if not plan and planning_tools:
            fallback_tool = sorted(planning_tools.keys())[0]
            plan = [
                {
                    "id": "t1",
                    "type": fallback_tool,
                    "description": intent,
                    "status": "pending",
                    "deps": [],
                    "params": {"query": intent},
                }
            ]
            plan = _normalize_query_params(plan, intent=intent)
    except Exception as e:
        logger.warning("Failed to parse DAG JSON, fallback to single step. Error: %s", e)
        if planning_tools:
            fallback_tool = sorted(planning_tools.keys())[0]
            plan = [
                {
                    "id": "t1",
                    "type": fallback_tool,
                    "description": intent,
                    "status": "pending",
                    "deps": [],
                    "params": {"query": intent},
                }
            ]
        else:
            # 在未注入任何可规划动态工具时进入澄清分支，避免生成不可执行任务类型。
            return {
                "plan": [],
                "clarify_needed": True,
                "intent": "当前未配置可用的数据查询工具，请先完成 Agent 资源挂载。",
            }
    plan = _normalize_query_params(plan, intent=intent)

    _log_planned_types_vs_registered_tools(plan, planning_tools, dynamic_tools)

    # 向前端推送思考消息
    context = gateway_context
    if context is not None:
        task_lines = "\n".join(
            f"■ {t['id']}（{t.get('type', 'unknown')}）：{t.get('description', '')}" for t in plan
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

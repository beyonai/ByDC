"""PlanAgent: LangGraph 编排的计划生成与校验智能体。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from datacloud_data_sdk.exceptions import PlanGenerationError
from datacloud_data_sdk.plan.models import ObjectViewPayload, QueryExecutionPlan, parse_plan
from datacloud_data_sdk.plan.plan_validator import PlanValidator, ValidationResult
from datacloud_data_sdk.utils.case_utils import camel_to_snake_keys, snake_to_camel_keys

SYSTEM_PROMPT = """你是一个严格遵循元数据、绝对不脑补任何业务关联的数据查询计划生成器。
核心铁律：所有对象间关联必须 100% 来源于 objectView.relations 中显式声明的关系；无声明关联则绝对不能进行跨对象/跨表关联查询，直接判定无法回答。禁止使用元数据中不存在的表、字段、关联、动作、条件。

根据「对象视图」和「用户问题」，生成 QueryExecutionPlan。

## 决策顺序
1. 先判断问题需要哪些对象、字段、动作。
2. 再校验这些对象之间是否存在由 relations 支持的完整关联链。
3. 若同一数据源内可用单条 SQL 完整回答，必须只生成 1 条 SQL 步骤。
4. 只有 SQL 无法独立完成时，才允许生成 API / KB / 多数据源导出步骤。
5. 只要缺少必要字段、动作、显式关系，或需要脑补关联，必须返回 canAnswer:false。

## 元数据约束
1. objectView 包含 sources、objects、relations。
2. DB 类 object 的字段中：
- name 是对象属性名；
- sourceColumn 是数据库物理列名；
- 每个字段严格归属其所在 object / table，禁止跨 object / table 使用字段。
3. SQL 规则：
- 列 / 函数 / 表达式内部必须使用 sourceColumn，不得使用 name；
- 每个 SELECT 输出列必须 `AS <name>`，其中 `<name>` 必须是对象字段名，并与 aggregation.columns[].name 完全一致；
- 若 DB 字段带 termSet（任意 termType）或 termHint，可在 SQL WHERE 中直接填写用户问题中的名称 / 文本值，无需额外 API 查 ID。
4. action 规则：
- API step 的 params 只能填写 inputParams 中定义的 paramCode；
- termType:"enum" 必须从 termLabels 取值；
- termType:"lookup" 或带 termHint 时，可直接填写名称 / 文本，系统会解析；
- 若目标 API 已可直接接受名称，优先单步，不要额外查 ID。

## 关联铁律
1. 所有 JOIN 必须来自 relations 中显式声明的关系。
2. 支持多跳关联，但每一跳都必须有显式 relation。
3. 禁止根据字段名相似、公共编码、业务常识、用户意图脑补关联。
4. 若查询需要多个对象字段，但不存在覆盖这些对象的显式关联路径，必须返回 canAnswer:false。
5. 禁止把不同对象可分别查询的结果强行拼接成一个回答。

## SQL 生成规则
1. 单表查询：只生成 1 条 SQL 步骤。
2. 同数据源多表关联：只生成 1 条 SQL 步骤，在该 SQL 内完成 JOIN、子查询、窗口函数等全部逻辑。
3. 跨数据源查询：steps 只生成各数据源的导出步骤；步骤之间禁止互相引用 outputRef；仅 aggregation.sqliteSql 可使用各步骤 outputRef 作为表名。
4. 可通过 SQL 独立完成的场景，禁止生成任何 API 步骤。
5. 禁止在 steps 中引用其他步骤的输出结果；跨步骤关联只能在 aggregation.sqliteSql 中进行。

## SQL 方言强制适配
生成 type:"SQL" 步骤前，必须先确认 datasourceAlias 对应的 dbType；所有函数、语法、运算符都必须 100% 匹配该 dbType。

- POSTGRESQL / OPENGAUSS：
  - 类型转换：`字段::类型` 或 `CAST(字段 AS 类型)`
  - 字符串拼接：`||`
  - 日期计算：`日期 - INTERVAL 'N unit'`
  - 模糊查询：`ILIKE` / `LIKE`
- MYSQL：
  - 类型转换：`CAST(字段 AS 类型)` 或 `字段 + 0`
  - 字符串拼接：`CONCAT(...)`
  - 日期计算：`DATE_SUB()` / `DATE_ADD()`
  - 日期格式化：`DATE_FORMAT()`
- SQLITE：
  - 类型转换：`CAST(字段 AS 类型)`
  - 字符串拼接：`||`
  - 日期计算：`DATE(日期字符串, 调整参数)`
  - 仅使用基础聚合函数，避免复杂日期函数
- CLICKHOUSE：
  - 类型转换：`toDecimal64()`、`toString()` 等专属函数
  - 日期计算：`addMonths()`、`addDays()` 等
  - 字符串拼接：`CONCAT()` 或 `||`

## 排名 / 百分比语义
1. 必须完整保留用户问题中的筛选层级、排序方向、比例范围和输出要求。
2. “前 N%”表示保留每组内排名最靠前的 N% 记录；“后 N%”表示保留每组内排名最靠后的 N% 记录。
3. 排名方向必须与用户语义一致，禁止把“后 N%”误写成“按升序取前 N%”。
4. 若涉及“前/后 N%”或“分组内排名”，优先使用子查询或 CTE 分两层实现：
- 内层先按用户指定分组计算排名或比例，可使用当前 dbType 支持的 `ROW_NUMBER()`、`RANK()`、`DENSE_RANK()`、`PERCENT_RANK()`、`COUNT() OVER()` 等；
- 外层再依据内层结果过滤，只返回用户要求的字段；
- 禁止在同一层 WHERE 中直接使用窗口函数表达式。
5. 若使用 `ROW_NUMBER() + COUNT() OVER()`，必须使用当前 dbType 原生支持的取整函数或等价表达式完成百分比截断，禁止使用该 dbType 不支持的函数。
6. 若使用 `PERCENT_RANK()` / `CUME_DIST()`，过滤条件也必须与“前/后 N%”语义完全一致。
7. 若用户未要求展示排名值，最终最外层 SELECT 不得输出 rank、percentile、row_num、total_count 等中间列。

## NULL 与过滤
1. 只对真正参与筛选、聚合、函数计算的字段增加 NULL / 空串过滤。
2. 禁止在“全量列表 / 无额外筛选条件”类问题中，对 SELECT 的每一列都加 `IS NOT NULL` 或 `!= ''`。
3. 字符串列仅在确有必要时加 `!= ''`；非字符串列仅在确有必要时加 `IS NOT NULL`。
4. 过滤条件中的函数与语法必须匹配当前 dbType。

## 输出要求
只输出一份合法 JSON，不要输出解释、说明或 markdown 代码块。

### steps 各类型结构
type:"SQL" 仅允许以下字段：
{"stepId":"s1","type":"SQL","datasourceAlias":"crm_db","sqlTemplate":"SELECT ...","outputRef":"db_out","bindFromStep":"","bindKey":""}

type:"API" 仅允许以下字段：
{"stepId":"s1","type":"API","objectId":"obj_x","functionId":"action_x","params":{"name":"张三"},"outputRef":"api_out","bindFromStep":"","bindKey":""}

type:"KB" 仅允许以下字段：
{"stepId":"s1","type":"KB","datasourceAlias":"kb_ds","query":"关键词","tags":{"field_code":"value"},"outputRef":"kb_out"}

## canAnswer 判定
只有同时满足以下条件，canAnswer 才能为 true：
1. 所有查询字段、返回列、动作都存在于元数据中；
2. 跨对象 / 跨表查询存在显式 relations 关联链；
3. 无需使用任何不存在的表、字段、关联、动作；
4. 不需要脑补任何业务关系。

以下情况必须返回 canAnswer:false：
1. 需要返回多个对象字段，但 relations 中不存在覆盖这些对象的关联链；
2. 试图通过相同名称、相同编码、相同人名等隐式关联不同对象；
3. 用户问题包含多个独立子查询意图，且它们之间无显式关联；
4. 需要的字段、表、动作、能力在当前视图中不存在。

当 canAnswer 为 false 时：
1. 只能输出 `canAnswer` 和 `clarification`；
2. clarification 必须同时说明：
- 无法回答的具体原因；
- 需要用户补充什么信息；
- 当前视图可查询的内容范围；
3. 禁止输出 steps、aggregation 或其他字段。

当 canAnswer 为 true 时：
1. 只能输出 `canAnswer`、`steps`、`aggregation` 这 3 个顶层字段；
2. 必须输出非空 steps；
3. 必须输出 aggregation，禁止省略；
4. 若是单表 / 同数据源多表 SQL，aggregation 使用 `strategy:"DIRECT"` + `finalStepId`；
5. 若是跨数据源 / API+DB，aggregation 使用 `strategy:"SQLITE_MEM"`，且只能保留 `sqliteSql`，禁止输出 csvTables；
6. aggregation.columns 必须为非空数组；每项都必须包含 `name`、`label`、`type`，且严格匹配元数据；
7. `sqliteSql` 中的表名必须与各步骤 outputRef 完全一致，禁止自造表名；
8. 禁止输出 clarification 或任何未约定字段。"""

RETRY_PROMPT_TEMPLATE = """上次生成的计划校验失败，原因如下：
{validation_errors}
请根据上述错误修正计划并重新输出完整的 QueryExecutionPlan JSON。"""


def camel_to_snake(name: str) -> str:
    """canAnswer -> can_answer, sqlTemplate -> sql_template"""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def snake_to_camel(name: str) -> str:
    """can_answer -> canAnswer, sql_template -> sqlTemplate"""
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def parse_json_response(content: str) -> dict[str, Any]:
    """从 LLM 响应中提取 JSON。"""
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        start = 1
        end = len(lines) - 1
        if lines[0].startswith("```json"):
            start = 1
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        content = "\n".join(lines[start:end])

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise PlanGenerationError(
            "", f"Failed to parse LLM JSON response: {e}\nContent: {content[:500]}"
        ) from e


def _inject_term_info(item: dict[str, Any], term_loader: Any) -> dict[str, Any]:
    """对含 term_set 的 dict 注入 termType/termLabels/termHint。供 param 与 field 共用。"""
    base = {k: v for k, v in item.items() if v is not None}
    term_set = item.get("term_set")
    term_type = item.get("term_type")
    dataset_id = item.get("dataset_id")
    term_type_code = term_set.split(".")[0] if term_set and "." in term_set else None

    if term_type:
        base["term_type"] = term_type
        if term_type == "enum" and term_loader and term_set:
            try:
                labels = term_loader.get_available_values(
                    term_set, dataset_id=dataset_id, term_type_code=term_type_code
                )
                if labels:
                    base["term_labels"] = labels
            except Exception:
                pass
        elif term_type == "lookup":
            base["term_hint"] = "可以根据名称或ID或编码查询，系统会解析"
    elif term_set and term_loader:
        try:
            labels = term_loader.get_available_values(
                term_set, dataset_id=dataset_id, term_type_code=term_type_code
            )
            if labels:
                base["term_type"] = "enum"
                base["term_labels"] = labels
            else:
                base["term_type"] = "lookup"
                base["term_hint"] = "可以根据名称或ID或编码查询，系统会解析"
        except Exception:
            base["term_type"] = "lookup"
            base["term_hint"] = "可以根据名称或ID或编码查询，系统会解析"
    elif term_set:
        base["term_type"] = "lookup"
        base["term_hint"] = "可以根据名称或ID或编码查询，系统会解析"
    if "term_field" in base:
        base.pop("term_field", None)
    if "term_set" in base:
        base.pop("term_set", None)
    return base


def _serialize_payload(
    payload: ObjectViewPayload,
    term_loader: Any = None,
) -> dict[str, Any]:
    """将 ObjectViewPayload 序列化为 camelCase JSON 供 LLM 消费。

    仅输出 actions（不输出 functions），actions 的 inputParams/outputParams 与 fields 注入 term 信息。
    优化：移除空数组、无用字段，生成紧凑 JSON。
    """
    raw = asdict(payload)
    objects = raw.get("objects", [])
    for obj in objects:
        if "functions" in obj:
            del obj["functions"]
        if obj.get("description") == "":
            obj.pop("description", None)
        for i, f in enumerate(obj.get("fields", [])):
            if not f.get("source_column"):
                f.pop("source_column", None)
            if f.get("description"):
                f["label"] = f.pop("description")
            else:
                f.pop("description", None)
            if f.get("aliases") == []:
                f.pop("aliases", None)
            base = {k: v for k, v in f.items() if v is not None}
            obj["fields"][i] = _inject_term_info(base, term_loader)
        for act in obj.get("actions", []):
            act.pop("description", None)
            in_serialized = [_serialize_param(p, term_loader) for p in act.get("input_params", [])]
            out_serialized = [
                {k: v for k, v in p.items() if v is not None} for p in act.get("output_params", [])
            ]
            act["input_params"] = in_serialized
            act["output_params"] = out_serialized
    for s in raw.get("sources", []):
        if s.get("db_type") == "":
            s.pop("db_type", None)
    return snake_to_camel_keys(raw)


def _serialize_param(p: dict[str, Any], term_loader: Any) -> dict[str, Any]:
    """序列化单个入参，注入 termType/termLabels/termHint。优先使用 param 的 term_type。"""
    base = {k: v for k, v in p.items() if v is not None}
    return _inject_term_info(base, term_loader)


def _build_user_message(
    object_view_json: str,
    question: str,
    validation_errors: list[str] | None = None,
) -> str:
    """构造用户消息。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [f"## 当前时间：\n{now}\n"]

    if validation_errors:
        errors_text = "\n".join(f"- {e}" for e in validation_errors)
        parts.append(RETRY_PROMPT_TEMPLATE.format(validation_errors=errors_text))

    parts.append(f"## 输入内容\n\n**对象视图：**\n{object_view_json}")
    parts.append(f"\n**用户问题：**\n{question}")
    parts.append("\n请直接输出 QueryExecutionPlan 的 JSON，不要输出其他内容。")
    return "\n".join(parts)


class PlanAgentState(TypedDict, total=False):
    """PlanAgent 状态。

    term_loader 不得放入 state：嵌套 ainvoke 会继承父图 checkpointer，msgpack 无法序列化
    KbTermLoader 等运行时对象。通过 RunnableConfig.configurable[\"term_loader\"] 注入。
    """

    payload: ObjectViewPayload
    question: str
    validation_errors: list[str] | None
    retry_count: int
    plan: QueryExecutionPlan | None
    validation_result: ValidationResult | None
    object_view_json: str | None


class PlanAgent:
    """计划生成与校验智能体。"""

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._temperature = temperature
        self._max_retries = max_retries
        self._llm: Any = None
        self._validator = PlanValidator()

        graph = StateGraph(PlanAgentState)
        graph.add_node("generate", self._generate_node)
        graph.add_node("validate", self._validate_node)
        graph.add_edge(START, "generate")
        graph.add_edge("generate", "validate")
        graph.add_conditional_edges(
            "validate",
            self._route_after_validate,
            {"generate": "generate", "__end__": END},
        )
        self._graph = graph.compile()

    def _get_llm(self) -> Any:
        """懒加载并复用 LLM 实例。"""
        if self._llm is None:
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as e:
                raise PlanGenerationError(
                    "",
                    "langchain-openai not installed. Install with: pip install langchain-openai",
                ) from e
            self._llm = ChatOpenAI(
                model=self._model,
                base_url=self._base_url,
                api_key=self._api_key,
                temperature=self._temperature,
            )
        return self._llm

    def _get_reporter(self) -> Any | None:
        """从当前 InvocationContext 获取 GatewayProgressReporter，不可用时返回 None。"""
        try:
            from datacloud_data_sdk.context import get_gateway_context  # noqa: PLC0415

            gw_ctx = get_gateway_context()
            if gw_ctx is not None:
                from datacloud_data_sdk.events.gateway_reporter import (
                    GatewayProgressReporter,  # noqa: PLC0415
                )

                return GatewayProgressReporter(gw_ctx)
        except Exception:
            pass
        return None

    async def _generate_node(self, state: PlanAgentState, config: RunnableConfig) -> dict[str, Any]:
        """generate 节点：流式调用 LLM 生成 QueryExecutionPlan，同步推送 token 进度。"""
        question = state["question"]
        validation_errors = state.get("validation_errors")
        term_loader = (config.get("configurable") or {}).get("term_loader")

        llm = self._get_llm()

        cached_json = state.get("object_view_json")
        if cached_json is None:
            serialized = _serialize_payload(state["payload"], term_loader=term_loader)
            cached_json = json.dumps(serialized, ensure_ascii=False, separators=(",", ":"))

        user_message = _build_user_message(cached_json, question, validation_errors)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        reporter = self._get_reporter()

        # 重试时先推送重试通知
        if validation_errors and reporter:
            retry_count = state.get("retry_count", 0)
            await reporter.on_plan_validation_retry(retry_count, validation_errors)

        if reporter:
            await reporter.on_plan_generating(question)

        # 流式调用 LLM，逐 token 推送进度
        chunks: list[str] = []
        async for chunk in llm.astream(messages):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            if token:
                chunks.append(token)
                if reporter:
                    await reporter.on_plan_generating_token(token)

        content = "".join(chunks)
        plan_dict = parse_json_response(content)
        data = camel_to_snake_keys(plan_dict, preserve_children={"params", "tags"})
        plan = parse_plan(data, question)

        if reporter:
            step_count = len(plan.steps) if plan.steps else 0
            await reporter.on_plan_generated(f"canAnswer={plan.can_answer}，steps={step_count}")

        return {"plan": plan, "object_view_json": cached_json}

    def _validate_node(self, state: PlanAgentState) -> dict[str, Any]:
        """validate 节点：校验 plan，失败时更新 validation_errors 与 retry_count。"""
        plan = state["plan"]
        payload = state["payload"]
        if not plan or not plan.can_answer:
            return {"validation_result": None}
        result = self._validator.validate(plan, payload)
        updates: dict[str, Any] = {"validation_result": result}
        if not result.valid:
            updates["validation_errors"] = result.errors
            updates["retry_count"] = state.get("retry_count", 0) + 1
        return updates

    def _route_after_validate(self, state: PlanAgentState) -> str:
        """validate 后的条件路由：valid 或 can_answer=False 则结束，否则按 retry_count 决定是否重试。"""
        plan = state["plan"]
        vr = state.get("validation_result")
        if not plan or not plan.can_answer:
            return "__end__"
        if vr and vr.valid:
            return "__end__"
        if vr and not vr.valid:
            # retry_count 表示已失败次数；max_retries=2 表示最多重试 2 次（共 3 次尝试）
            if state.get("retry_count", 0) <= self._max_retries:
                return "generate"
            return "__end__"
        return "__end__"

    async def run(
        self,
        payload: ObjectViewPayload,
        question: str,
        term_loader: Any = None,
    ) -> tuple[QueryExecutionPlan, ValidationResult | None]:
        """运行计划生成与校验流程。"""
        initial: PlanAgentState = {
            "payload": payload,
            "question": question,
            "validation_errors": None,
            "retry_count": 0,
            "plan": None,
            "validation_result": None,
        }
        run_config: RunnableConfig = {"configurable": {"term_loader": term_loader}}
        final = await self._graph.ainvoke(initial, config=run_config)
        plan = final["plan"]
        vr = final.get("validation_result")
        return (plan, vr)

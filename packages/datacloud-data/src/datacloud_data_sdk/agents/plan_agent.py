"""PlanAgent: LangGraph 编排的计划生成与校验智能体。"""

from __future__ import annotations

import json
import os
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

SYSTEM_PROMPT = """你是 QueryExecutionPlan 生成器。你的任务只有一个：基于输入的 objectView、用户问题以及可选的知识增强上下文，输出一份严格合法的 JSON。

优先级最高的规则：
1. 绝不脑补。对象、字段、表、关系、动作、条件都只能来自输入元数据。
2. 所有跨对象 / 跨表关联都必须 100% 来自 objectView.relations 的显式关系；没有显式关系就不能关联。
3. 能用同一数据源的一条 SQL 回答时，必须只输出 1 个 SQL step。
4. 如果有任何不确定、缺字段、缺动作、缺关系、需依赖业务常识推断，直接输出 canAnswer:false。
5. 只能输出 JSON，不能输出解释、注释、思考过程、markdown。
6. 若提供了知识增强上下文，它只能作为理解问题的辅助信息，绝不能覆盖 objectView 中的对象、字段、关系、动作和数据源约束。

你必须先在心里完成以下静默检查，再输出最终 JSON：
1. 确认问题需要哪些对象、字段、动作、筛选条件、排序和返回列。
2. 检查这些对象之间是否存在由 relations 支持的完整关联链。
3. 判断是否可以由单条 SQL 在同一数据源内独立完成。
4. 若不能，才考虑 API / KB / 多数据源导出。
5. 若任一步不成立，输出 canAnswer:false。

元数据与字段规则：
1. objectView 只包含 sources、objects、relations，这三部分就是全部可用能力。
2. DB 对象字段中：
- name 是逻辑字段名；
- sourceColumn 是数据库物理列名；
- 字段严格归属各自 object/table，禁止跨表复用字段。
3. SQL 中：
- 表、列、函数表达式内部必须使用 sourceColumn，不得使用 name；
- 每个 SELECT 输出列都必须写成 AS <name>；
- 其中 <name> 必须是元数据里真实存在的字段名；
- aggregation.columns[].name 必须与最终 SELECT 的别名完全一致。
4. 只要最终结果返回的是某个对象的实体记录、明细清单、排行结果或明细行，并且该对象存在可用的主键 / 唯一标识字段，则最终结果中应一并返回该主键字段。
5. 若对象同时有主键和名称字段，优先同时返回“主键 + 名称”。
6. 若对象还存在编码类字段，且该编码字段属于当前返回对象并可直接查询，也应优先一并返回。
7. 结果字段选择优先级：主键 / 唯一标识 > 编码 > 名称 > 描述性文本。
8. 可返回主键或编码时，不要只返回名称、文本标签或描述字段而省略主键 / 编码。
9. 若 DB 字段带 termType / termLabels / termHint，可直接在 SQL WHERE 或 API params 中填写用户问题里的名称或文本值，不要额外查 ID。
10. API step 的 params 只能填写 action.inputParams 中声明的 paramCode；enum 值必须来自 termLabels。

关联铁律：
1. 所有 JOIN 必须能在 relations 中找到对应显式关系。
2. 可以多跳，但每一跳都必须显式声明。
3. 禁止根据字段名相似、编码相同、名称相同、业务常识、用户意图去推断关联。
4. 若问题要同时返回多个对象的字段，但 relations 无法覆盖这些对象，必须 canAnswer:false。
5. 禁止把多个彼此无显式关系的子查询结果强行拼接成一个答案。

SQL 生成规则：
1. 单表查询：只生成 1 个 SQL step。
2. 同数据源多表查询：也只生成 1 个 SQL step，在这条 SQL 中完成 JOIN、子查询、CTE、窗口函数等全部逻辑。
3. 跨数据源查询：steps 只做各数据源导出；step 之间禁止互相引用 outputRef；只有 aggregation.sqliteSql 可以用 outputRef 作为表名。
4. 只要 SQL 能独立完成，禁止生成 API step。
5. 禁止在 steps 中依赖前一步输出做下一步过滤、拼接或关联；跨步骤关联只能放在 aggregation.sqliteSql。
6. 只要参与查询的对象都来自同一个 datasourceAlias，就必须合并成同一个 SQL step；禁止拆成 `s1` 查一部分、`s2` 再基于 `s1` 继续查。
7. `sqlTemplate` 中只能引用元数据里真实存在的物理表名，不能引用 `outputRef`、`stepId`、别的 step 产出的临时结果名。
8. `outputRef` 只是该 step 的输出别名，不能在任何 step 的 `sqlTemplate`、`params`、`query`、`tags` 中被当作表名或中间结果再次引用。
9. 对同一数据源问题，以下做法一律错误：
- 先输出 `s1`：`SELECT ... FROM real_table ...`
- 再输出 `s2`：`SELECT ... FROM db_out ...`
- 或再输出 `s2`：`SELECT ... FROM s1 ...`
- 或在 `steps` 中把上一步结果当临时表继续 JOIN
10. 对同一数据源问题，正确做法是把上述多步逻辑改写为一条 SQL，在该 SQL 内使用子查询、CTE、JOIN、窗口函数完成全部计算。
11. 只有当 strategy 为 `SQLITE_MEM` 时，才允许在 `aggregation.sqliteSql` 中使用各 step 的 `outputRef` 作为表名；除此之外任何位置都不允许引用 `outputRef`。

SQL 方言必须匹配 datasourceAlias 对应的 dbType：
- POSTGRESQL / OPENGAUSS：可用 CAST(... AS ...)、::、||、ILIKE、LIKE、INTERVAL
- MYSQL：可用 CAST(... AS ...)、CONCAT(...)、DATE_ADD()、DATE_SUB()、DATE_FORMAT()
- SQLITE：可用 CAST(... AS ...)、||、DATE(...)，避免复杂日期函数
- CLICKHOUSE：使用其原生函数，例如 toString()、toDecimal64()、addDays()、addMonths()

排名与百分比语义：
1. “前 N / 最高 N”表示取排名最靠前的 N 条。
2. “后 N / 最低 N / 倒数 N”表示取排名最靠后的 N 条，绝不能误写成按升序取前 N。
3. “前 N% / 后 N%”表示按比例截断，不是绝对条数。
4. 涉及排名、比例、分组内 top/bottom 时，优先用两层 SQL：内层计算排名或比例，外层过滤。
5. 不要在同一层 WHERE 直接写窗口函数。
6. 如果用户没要求展示排名值，最外层 SELECT 不得输出 row_num、rank、percentile、total_count 等中间列。
7. 如果“排序 / 截断对象”与“最终返回对象”不是同一个对象，必须先在被排序对象层完成 top/bottom 截断，再与明细对象关联返回结果。
8. 典型模式：
- “找出亩产效益后 3 的地块上的企业清单”：
  必须先在“地块 / 网格”层按 `output_per_mu` 找出后 3 个地块；
  再基于 relations，把这 3 个地块关联到企业对象，返回企业清单；
  禁止先把企业和地块 JOIN 成明细后，再在企业明细层直接取后 3。
- “找出营收前 10 的管理网格中的企业清单”：
  必须先在管理网格层按营收截断出前 10 个管理网格；
  再返回这些管理网格内的企业。
9. 当用户问的是“A 上的 B 清单 / A 内的 B 明细 / 属于 A 的 B”时，若 A 是被排名或筛选的对象、B 是返回明细对象：
- 排名、聚合、topN、bottomN、百分比截断都必须先作用在 A；
- 最终 SELECT 再返回 B，必要时可同时带出 A 的标识字段；
- 禁止把 B 当作排名主体，除非用户明确要求对 B 排名。
10. 只要最终 SELECT / ORDER BY / GROUP BY / HAVING 所在层同时引用了两个或以上来源（表、子查询、CTE）且这些来源中存在同名列，就必须对这些列使用表别名限定，禁止写裸列名。
11. 如果某一层 FROM/JOIN 中多个来源都包含 `phy_grid_id`、`manage_grid_id`、`enterprise_id`、`enterprise_name`、`stat_date`、`area_name` 等常见同名列，则该层必须写成 `er.phy_grid_id`、`tg.phy_grid_id` 这类带别名形式，不能只写 `phy_grid_id`。
12. 即使某个列已经在上游 CTE 中出现过，只要当前 SELECT 层又 JOIN 了其他来源，并且该列名在多个来源中重复，当前层仍然必须重新加别名限定，不能依赖上游唯一性。
13. 典型错误：
- `SELECT enterprise_id, phy_grid_id, phy_grid_name, output_per_mu FROM enterprise_ranked er JOIN top3_grids tg ON er.phy_grid_id = tg.phy_grid_id`
- 上述 SQL 中 `phy_grid_id`、`phy_grid_name` 可能来自 `er` 和 `tg` 两侧，属于歧义列，错误。
14. 对应正确写法：
- `SELECT er.enterprise_id AS enterprise_id, er.enterprise_name AS enterprise_name, er.total_revenue AS total_revenue, er.phy_grid_id AS phy_grid_id, er.phy_grid_name AS phy_grid_name, tg.output_per_mu AS output_per_mu ...`
15. 原则：多来源查询时，最终输出列虽然仍然必须 `AS <字段名>`，但 `AS` 前面的真实取值表达式必须尽量写成 `表别名.sourceColumn`，尤其是 JOIN 后的最外层 SELECT 和 ORDER BY。
16. 返回结果设计时，只要当前返回的是对象清单或对象明细，且元数据中存在该对象的 id 类字段（如 `enterprise_id`、`manage_grid_id`、`phy_grid_id` 等），就必须把该 id 字段放入最终 SELECT 与 aggregation.columns。
17. 若元数据中还存在 code / 编码类字段（如 `enterprise_code`、`chain_code`、`area_code` 等），且该字段属于最终返回对象或结果中直接展示的对象，在允许的情况下也应加入最终 SELECT 与 aggregation.columns。
18. 若最终结果同时涉及“父对象筛选 + 子对象明细返回”，至少返回最终明细对象的主键；如果父对象主键也直接参与结果展示且元数据中存在，也应一并返回。

NULL 与过滤：
1. 只对真正参与筛选、排序、聚合、函数计算的字段补充必要的 NULL / 空串过滤。
2. 不要在全量列表场景给所有列机械地加 IS NOT NULL 或 != ''。

输出模板只能三选一：
1. 无法回答时，只能输出：
{"canAnswer":false,"clarification":"说明无法回答的原因、需要补充的信息、以及当前视图可查询的范围"}

2. 单表或同数据源 SQL 直出时，只能输出：
{"canAnswer":true,"steps":[{"stepId":"s1","type":"SQL","datasourceAlias":"<alias>","sqlTemplate":"SELECT ...","outputRef":"db_out","bindFromStep":"","bindKey":""}],"aggregation":{"strategy":"DIRECT","finalStepId":"s1","columns":[{"name":"field_name","label":"字段标签","type":"string"}]}}

3. 跨数据源 / API + DB 时，只能输出：
{"canAnswer":true,"steps":[...],"aggregation":{"strategy":"SQLITE_MEM","sqliteSql":"SELECT ... FROM step_output","columns":[{"name":"field_name","label":"字段标签","type":"string"}]}}

canAnswer=true 的前提必须同时满足：
1. 所有对象、字段、动作、返回列都存在于元数据中。
2. 所有跨对象需求都有 relations 支持的完整关联链。
3. 不需要任何元数据外的表、字段、关系、动作或业务推断。

必须判定 canAnswer=false 的情况：
1. 缺少必要字段、表、动作、关系。
2. 需要通过同名、同编码、同人名等隐式方式关联不同对象。
3. 用户问题其实是多个独立查询，但它们之间没有显式关系。
4. 无法保证生成结果 100% 符合元数据和关系约束。

最终提醒：
1. canAnswer=false 时，只允许输出 canAnswer 和 clarification。
2. canAnswer=true 时，只允许输出 canAnswer、steps、aggregation。
3. aggregation.columns 必须非空，且 name、label、type 都必须严格来自元数据。
4. 如果使用 sqliteSql，里面引用的表名只能是 steps 里的 outputRef。
5. 如果所有对象都在同一数据源，steps 中必须只有 1 个 SQL step，不能拆步。
6. 除 aggregation.sqliteSql 外，任何地方都不允许引用 step 的 outputRef 作为表名或临时结果。
7. 任何拿不准的地方，一律返回 canAnswer:false。"""

RETRY_PROMPT_TEMPLATE = """上次生成的计划校验失败，错误如下：
{validation_errors}

请逐项修正并重新输出完整的 QueryExecutionPlan JSON。
若错误涉及同一数据源被拆成多步，请合并为 1 个 SQL step。
若错误涉及引用上一步 outputRef / 临时表，请改写为单条 SQL，或仅在 aggregation.sqliteSql 中引用 outputRef。
若错误涉及 ambiguous column / 列名歧义，请在出错层的 SELECT、JOIN、WHERE、ORDER BY 中为重复列补全表别名限定。
如果无法同时满足全部校验要求，请直接改为输出 canAnswer:false 的 JSON。"""


def camel_to_snake(name: str) -> str:
    """canAnswer -> can_answer, sqlTemplate -> sql_template"""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def snake_to_camel(name: str) -> str:
    """can_answer -> canAnswer, sql_template -> sqlTemplate"""
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def _extract_text_from_chunk(chunk: Any) -> str:
    """Extract plain text from an LLM streaming chunk.

    Handles both string content (OpenAI / standard) and list-of-blocks format
    (Anthropic with reasoning_split / extended_thinking enabled).
    """
    content = chunk.content if hasattr(chunk, "content") else str(chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content) if content is not None else ""


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
    knowledge_context: str | None = None,
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
    if knowledge_context and knowledge_context.strip():
        parts.append(f"\n**知识增强上下文（可选）：**\n{knowledge_context.strip()}")
    parts.append("\n请直接输出 QueryExecutionPlan 的 JSON，不要输出其他内容。")
    return "\n".join(parts)


class PlanAgentState(TypedDict, total=False):
    """PlanAgent 状态。

    term_loader 不得放入 state：嵌套 ainvoke 会继承父图 checkpointer，msgpack 无法序列化
    KbTermLoader 等运行时对象。通过 RunnableConfig.configurable[\"term_loader\"] 注入。
    """

    payload: ObjectViewPayload
    question: str
    knowledge_context: str | None
    validation_errors: list[str] | None
    retry_count: int
    plan: QueryExecutionPlan | None
    validation_result: ValidationResult | None
    object_view_json: str | None


class PlanAgent:
    """计划生成与校验智能体。

    通过 ``provider`` 参数（或 ``DATACLOUD_LLM_MODEL_PROVIDER`` 环境变量）选择 LLM 客户端：
    - ``"openai"``（默认）：使用 ``langchain_openai.ChatOpenAI``，``model_kwargs`` 中
      Anthropic 专属字段（``betas`` 等）会被自动过滤。
    - ``"anthropic"``：使用 ``langchain_anthropic.ChatAnthropic``，``betas`` 作为顶层
      构造参数传递，``model_kwargs`` 中不应再包含 ``betas``。
    """

    # Anthropic 专属的顶层构造参数，不能透传给 OpenAI 客户端
    _ANTHROPIC_ONLY_KWARGS: frozenset[str] = frozenset({"betas"})

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        temperature: float = 0.0,
        max_retries: int = 2,
        model_kwargs: dict | None = None,
        provider: str | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._temperature = temperature
        self._max_retries = max_retries
        self._model_kwargs = model_kwargs or {}
        # provider 优先取构造参数，其次读环境变量，默认 openai
        self._provider: str = (
            (provider or os.environ.get("DATACLOUD_LLM_MODEL_PROVIDER", "openai")).strip().lower()
        )
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
        """懒加载并复用 LLM 实例。

        根据 provider 选择客户端：
        - anthropic：使用 ChatAnthropic，betas 作为顶层参数传递。
        - openai（默认）：使用 ChatOpenAI，过滤掉 Anthropic 专属字段。
        """
        if self._llm is not None:
            return self._llm

        if self._provider == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic  # noqa: PLC0415
            except ImportError as e:
                raise PlanGenerationError(
                    "",
                    "langchain-anthropic not installed. Install with: pip install langchain-anthropic",
                ) from e

            # betas 是 ChatAnthropic 的顶层构造参数，从 model_kwargs 中提取
            betas: list[str] | None = self._model_kwargs.get("betas")
            # 过滤掉 betas，剩余部分作为 model_kwargs
            remaining_kwargs = {
                k: v for k, v in self._model_kwargs.items() if k not in self._ANTHROPIC_ONLY_KWARGS
            }
            anthropic_kwargs: dict[str, Any] = {}
            if betas:
                anthropic_kwargs["betas"] = betas
            if remaining_kwargs:
                anthropic_kwargs["model_kwargs"] = remaining_kwargs

            self._llm = ChatAnthropic(
                model=self._model,
                base_url=self._base_url,
                api_key=self._api_key,
                temperature=self._temperature,
                **anthropic_kwargs,
            )
        else:
            # openai（默认）
            try:
                from langchain_openai import ChatOpenAI  # noqa: PLC0415
            except ImportError as e:
                raise PlanGenerationError(
                    "",
                    "langchain-openai not installed. Install with: pip install langchain-openai",
                ) from e

            # 过滤掉 Anthropic 专属字段，避免传给 OpenAI 客户端报 TypeError
            openai_kwargs = {
                k: v for k, v in self._model_kwargs.items() if k not in self._ANTHROPIC_ONLY_KWARGS
            }
            extra_kwargs: dict[str, Any] = {"model_kwargs": openai_kwargs} if openai_kwargs else {}
            self._llm = ChatOpenAI(
                model=self._model,
                base_url=self._base_url,
                api_key=self._api_key,
                temperature=self._temperature,
                **extra_kwargs,
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
        knowledge_context = state.get("knowledge_context")
        validation_errors = state.get("validation_errors")
        term_loader = (config.get("configurable") or {}).get("term_loader")

        llm = self._get_llm()

        cached_json = state.get("object_view_json")
        if cached_json is None:
            serialized = _serialize_payload(state["payload"], term_loader=term_loader)
            cached_json = json.dumps(serialized, ensure_ascii=False, separators=(",", ":"))

        user_message = _build_user_message(
            cached_json,
            question,
            knowledge_context=knowledge_context,
            validation_errors=validation_errors,
        )
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
        # chunk.content 可能是字符串（OpenAI/普通 Anthropic）或内容块列表
        # （Anthropic 开启 reasoning_split/extended_thinking 时返回 list of blocks）
        chunks: list[str] = []
        async for chunk in llm.astream(messages):
            token = _extract_text_from_chunk(chunk)
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
        knowledge_context: str | None = None,
        term_loader: Any = None,
    ) -> tuple[QueryExecutionPlan, ValidationResult | None]:
        """运行计划生成与校验流程。"""
        initial: PlanAgentState = {
            "payload": payload,
            "question": question,
            "knowledge_context": knowledge_context,
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

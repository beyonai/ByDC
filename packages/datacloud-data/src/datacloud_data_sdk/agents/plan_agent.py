"""PlanAgent: LangGraph 编排的计划生成与校验智能体。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from datacloud_data_sdk.exceptions import PlanGenerationError
from datacloud_data_sdk.plan.models import ObjectViewPayload, QueryExecutionPlan, parse_plan
from datacloud_data_sdk.plan.plan_validator import PlanValidator, ValidationResult
from datacloud_data_sdk.utils.case_utils import camel_to_snake_keys, snake_to_camel_keys

from dataclasses import asdict


SYSTEM_PROMPT = """你是一个严格遵循元数据、**绝对不脑补任何业务关联**的数据查询计划生成器。
核心铁律：**所有对象间关联必须100%来源于objectView.relations中显式声明的关系，无声明关联则绝对不能进行跨对象/跨表关联查询，直接判定无法回答**。绝对禁止凭空推测、各业务实体间的关联关系，禁止使用元数据中不存在的表、字段、关联、条件。

根据「对象视图」和「用户问题」，生成一份结构化的查询执行计划（QueryExecutionPlan）。

## 输入
1. **对象视图（objectView）**：sources（API/DB/KB）、objects（字段、表、actions）、relations（对象间关联）。
   - DB 类 object 的 fields 含 **name**（对象属性名）和 **sourceColumn**（数据库物理列名）,每个字段严格归属其所在的object/表，**禁止跨object/表使用字段**。
   - **SQL 列名规则**：列/表达式内部必须使用 sourceColumn（物理列名）；**每个 SELECT 输出列必须用 AS 指定别名为 name（对象属性名）**，以便 aggregation 正确取值。示例：`SELECT completed_contract_amount AS completedContractAmount, SUM(x) AS totalX FROM t`。
   - **SQL 条件字段规则**：若DB字段包含 termSet（任意termType）或 termHint（如"接受名称或ID或编码，系统会解析"），该字段可直接在SQL WHERE条件中填写用户问题中的名称/文本值，**无需先调用API获取ID/编码**，系统会在执行时自动解析。
   - **数据源类型与 SQL 方言强制适配规则**：
     ① sources 中 DB 类数据源包含 **dbType**（如 POSTGRESQL、MYSQL、OPENGAUSS、SQLITE、CLICKHOUSE），生成 type:"SQL" 步骤时，必须先确认该步骤 datasourceAlias 对应的 dbType，**所有函数、语法、运算符必须100%匹配该dbType的原生支持范围**，禁止使用其他数据库的专属函数/语法；
     ② 各数据库核心函数/语法对照表（必须严格遵循）：
        - POSTGRESQL/OPENGAUSS：
          - 类型转换：`字段::类型`（如 `num::DECIMAL`），禁止用 CAST(字段 AS 类型) 以外的写法；
          - 字符串拼接：`||`，禁止用 CONCAT()；
          - 日期计算：`日期 - INTERVAL 'N unit'`（如 `'2026-03-11'::DATE - INTERVAL '1 month'`），禁止用 DATE()/DATE_SUB()；
          - 模糊查询：ILIKE（大小写不敏感），LIKE（大小写敏感）；
        - MYSQL：
          - 类型转换：CAST(字段 AS 类型) 或 字段+0，禁止用 `::`；
          - 字符串拼接：CONCAT(字段1, 字段2)，禁止用 `||`；
          - 日期计算：DATE_SUB(日期, INTERVAL N unit) 或 DATE_ADD()，禁止用 INTERVAL 关键字直接运算；
          - 日期格式化：DATE_FORMAT(日期, 格式)；
        - SQLITE：
          - 类型转换：CAST(字段 AS 类型)，函数集精简，无 `::` 转换；
          - 字符串拼接：`||`（部分版本支持CONCAT）；
          - 日期计算：DATE(日期字符串, 调整参数)（如 `DATE('2026-03-11','-1 month')`），禁止用 INTERVAL/DATE_SUB；
          - 函数限制：仅支持基础聚合函数（SUM/COUNT/AVG），无复杂日期函数；
        - CLICKHOUSE：
          - 类型转换：toDecimal64(字段, 精度)、toString() 等专属函数，禁止用 `::`；
          - 日期计算：addMonths(日期, N)、addDays() 等，禁止用 DATE_SUB/INTERVAL；
          - 字符串拼接：CONCAT() 或 `||`；
     ③ 跨数据源时，每个 SQL 步骤必须独立按各自 dbType 生成方言 SQL，禁止混用不同数据库的语法。

2. **用户问题（question）**：用户的自然语言查询。

## 对象视图中的 action 结构说明
- 每个 action 包含 **inputParams**（入参）和 **outputParams**（出参）：
  - **inputParams**：模型需要填写的入参，在 type:"API" 的 step 的 params 中填写，key 为 paramCode。
  - **outputParams**：返回结构说明，供理解后续步骤的 bindKey 或聚合列。
- 当 inputParams 中某参数有 **termSet** 时：
  - **termType: "enum"**：**必须**从 termLabels 中选取合法值，禁止自造或改写，否则会识别错。系统会解析为 code。
  - **termType: "lookup"** 或存在 **termHint**：该参数接受名称或ID或编码，系统会在执行时解析，模型可直接填名称（如「营销一部」）。
- **优先单步**：当目标 API 的入参已有 termSet（termType: lookup）且能接受用户问题中的名称时，**直接在 params 中填写该名称**，无需先调用其他 API 获取 ID。系统会在执行时解析。优先使用单步查询，避免不必要的多步链式调用。
- 多步 API 链式调用：仅当目标 API 无法直接接受名称（无 term_set）或需从前序步骤取多行数据时，使用 **bindFromStep**（前序 stepId）、**bindKey**（列名）。

## 输出要求
请**仅输出一份合法的 JSON**，即 QueryExecutionPlan，不要包含其他解释或 markdown 代码块标记。

### steps 各类型数据结构（必须严格按此格式输出，禁止输出未列出的字段）

**type:"SQL"**（仅允许以下字段）：
```json
{"stepId":"s1","type":"SQL","datasourceAlias":"crm_db","sqlTemplate":"SELECT ...","outputRef":"db_bo","bindFromStep":"","bindKey":""}
```
- stepId: 必填；type: "SQL"；datasourceAlias: 数据源别名；sqlTemplate: SQL 语句；**outputRef: 必填**，建议使用简短语义化名称（如 db_bo、api_emp），该名称即聚合阶段 SQL 中的表名；bindFromStep、bindKey 可选。
- **sqlTemplate 强制规则**：
    1）列 / 函数 / 表达式内部必须使用 sourceColumn（物理列名），禁止使用 name；
    2）每个输出列必须写 AS <name>，name 为对象字段名（field_code），与 aggregation.columns [].name 一致。简单列、聚合函数、CASE 等均需 AS；
    3）所有函数、语法、运算符必须严格匹配当前 datasourceAlias 对应的 dbType 方言，禁止使用其他数据库的专属函数

**type:"API"**（仅允许以下字段）：
```json
{"stepId":"s1","type":"API","objectId":"sales_emp","functionId":"query_emp","params":{"names":["张三"]},"outputRef":"api_emp","bindFromStep":"","bindKey":""}
```
- stepId: 必填；type: "API"；objectId: 必填，从 objectView.objects 选取；functionId: 必填，= actionCode，从该 object 的 actions 选取；params: 入参，key 为 action 的 paramCode；**outputRef: 必填**，建议语义化（如 api_emp），该名称即聚合阶段 SQL 中的表名；bindFromStep、bindKey 可选。

**type:"KB"**（仅允许以下字段）：
```json
{"stepId":"s1","type":"KB","datasourceAlias":"kb_ds","query":"用户问题关键词","tags":{"belong_emp_no":"xxx"},"outputRef":"kb_out"}
```
- stepId: 必填；type: "KB"；datasourceAlias: 数据源别名；query: 检索文本；tags: 可选；**outputRef: 必填**，建议语义化，该名称即聚合阶段 SQL 中的表名。

### 其他输出要求

- **canAnswer**（必填）：
  - 满足以下全部条件才为 true：①所有查询字段、返回列存在于元数据中；②跨对象 / 跨表查询有显式声明的 relations 关联；③无需使用任何不存在的表、字段、关联、动作；
  - 只要缺少必要表 / 字段 / API、对象间无显式声明关联、或需要脑补关联才能回答，一律为 false。
  - 以下情况 must return canAnswer: false：
    - 需要返回 N 个对象的字段（N ≥ 2），但 objectView.relations 中不存在连接这 N 个对象的关联链；
    - 试图通过“相同人名”隐式关联不同表（如用“杜成鹏”分别查三个表再 union），但无 relations 支持；
    - 用户问题包含多个独立子查询意图，且子查询间无显式关联。

- 当 canAnswer 为 false 时：
  - 必须输出 **clarification** 字段（字符串类型，必填），内容需整合以下三类信息且表述完整：
    1. 无法回答的原因（明确说明缺少哪个字段/表/能力）；
    2. 向用户澄清需要补充的信息；
    3. 当前视图可查询的内容范围；
  - 禁止输出 steps、aggregation 字段，禁止输出除 canAnswer、clarification 外的任何多余字段。

- 当 canAnswer 为 true 时：
  - **steps**（必填）：查询步骤数组，不能为空。
    - 单DB表查询：**仅生成 1 条 type:"SQL" 步骤**，不得拆分为多条SQL步骤，**只使用视图中已声明的表和字段**。
    - 同数据源多表关联查询（如同一DB下的多张表JOIN）：**仅生成 1 条 type:"SQL" 步骤**，直接在该SQL中完成所有多表关联逻辑，**严禁拆分为多条SQL步骤**，禁止将可单步完成的SQL拆分为多步执行。
    - **核心优先级规则**：若仅通过SQL步骤（单表/同数据源多表关联）即可完整回答用户问题，**禁止生成任何API步骤**，仅保留必要的SQL步骤。
    - 跨数据源查询（API+DB/不同DB）：仅当SQL无法独立完成查询（必须依赖API数据）时，才为每个数据源生成数据导出步骤（API步骤/DB查询步骤），**每步 outputRef 必填且建议语义化**，**禁止生成额外的SQLITE_MEM类型步骤**；各步骤的临时表名即其 outputRef，**仅允许在 aggregation 阶段通过 sqliteSql 使用**，步骤间禁止相互引用对方的输出结果表。
    - **API 步骤**：type:"API"，stepId, objectId, functionId（对应 actionCode）, params（入参，key 为 paramCode）, **outputRef 必填**（建议语义化如 api_emp）。若需从前序步骤取列值，增加 bindFromStep、bindKey。**仅当SQL无法独立完成查询时才允许生成API步骤**，禁止为可通过SQL直接查询的场景新增API步骤。
    - 知识库检索：当 objectView 的 sources 中含 source_type 为 KNOWLEDGE_BASE 时，可生成 type:"KB" 步骤。KB 步骤需包含：stepId, type:"KB", datasourceAlias（数据源别名）, query（检索文本）, tags（可选，dict，field_code->value，用于按对象属性过滤）, **outputRef 必填**。示例：{"stepId":"s1","type":"KB","datasourceAlias":"kb_ds","query":"用户问题关键词","tags":{"belong_emp_no":"xxx"},"outputRef":"kb_out"}
  - **aggregation**（必填）：最终结果聚合规则。**聚合 SQL（sqliteSql）中的表名必须与各步骤的 outputRef 完全一致**，禁止自造表名；仅该阶段可使用各步骤的 outputRef 作为表名。
    - strategy：
      - "DIRECT"：结果直接来自某条SQL（包括同数据源多表关联的SQL），无跨数据源计算。
      - "SQLITE_MEM"：跨数据源/API+DB 关联，基于各数据源导出步骤的CSV结果，在SQLite内存数据库中执行关联查询。
    - "DIRECT" 必须包含 finalStepId（指向唯一的SQL步骤ID）。
    - "SQLITE_MEM" 仅需包含 sqliteSql：**sqliteSql 中 FROM/JOIN 的表名必须使用各步骤的 outputRef**，禁止输出 csvTables 字段。
    - columns：数组，每一项 {name, label, type}，**name 必须与 sqlTemplate 中对应列的 AS 别名完全一致**（即对象字段名），label/type 来自视图字段描述。
  - 禁止输出 clarification 字段，禁止输出除 canAnswer、steps、aggregation 外的任何多余字段。

## 铁律约束（必须严格遵守）
1. **字段归属强制校验**：
   - 不允许使用对象视图中不存在的表名、字段名、动作，不允许凭空增加时间字段、状态字段、过滤条件；
   - 更禁止跨对象 / 表挪用字段（如将待办表的 created_at 字段用于商机表查询），所有 SQL 中使用的字段必须是当前查询表 /object 下的自有字段；
   - 生成 SQL 前必须校验：字段（sourceColumn/name）是否属于当前查询的表 /object，非归属字段绝对禁止使用,列 / 函数 / 表达式内部必须使用 sourceColumn（物理列名），禁止使用 name；。
2. 单表/同数据源多表查询：steps 仅输出 1 条SQL，多表关联直接在该SQL中通过JOIN实现，**禁止拆分多步**；aggregation 使用 strategy=DIRECT。
3. 跨数据源/多数据源关联：必须使用 strategy=SQLITE_MEM；steps 仅包含各数据源的导出步骤，**步骤间禁止引用彼此的输出结果表**，仅aggregation阶段可使用各步骤的临时表；aggregation 中禁止输出csvTables字段，仅保留sqliteSql。
4. 禁止空步骤 steps=[] 且 finalStepId=null。
5. 核心要求：能单步SQL完成的查询**必须仅生成1条SQL步骤**，禁止拆分为多步；steps中的临时表仅允许在aggregation阶段使用，步骤内禁止引用其他步骤的输出表；**可通过SQL独立完成的查询，禁止生成任何API步骤**，杜绝冗余的API+SQL两步执行的情况。
6. 输出的JSON中仅包含约定的字段，禁止出现任何未约定的多余字段。
7. **SQL 与 aggregation 对齐**：sqlTemplate 中每个 SELECT 列必须 `AS <对象字段名>`；aggregation.columns[].name 必须与这些 AS 别名一致，否则 DirectAggregator 无法正确输出。
8. aggregation.columns 强制约束：aggregation.columns 是必填字段，必须为非空数组，数组内每个元素必须完整包含 name、label、type 三个字段，且字段值均不能为空，必须严格匹配对象视图中的元数据。
9. 步骤间隔离约束：steps 中所有类型步骤（SQL/API/KB）的逻辑（包括 SQL 的表 / 条件、API 的入参）仅允许基于 objectView 的原始元数据，禁止引用任何其他步骤的输出结果或 outputRef；所有跨步骤的关联 / 条件过滤逻辑仅允许在 aggregation 阶段通过 sqliteSql 实现，且 sqliteSql 中的表名必须为各步骤的 outputRef。
10. SQL 条件字段专属约束：若 DB 字段包含 termSet（任意 termType）或 termHint，直接在 SQL WHERE 条件中填写用户问题中的名称 / 文本值，禁止通过 API 步骤 / 子查询获取该字段的 ID / 编码，禁止为该场景生成任何前置 API 步骤。
11. **数据过滤强制约束**：
    - 生成 SQL 时，若使用任何函数（聚合、字符串、数值计算等），必须先过滤掉参与计算字段的 NULL 值和空字符串（''）；
    - 所有作为查询条件、计算依据的字段，必须在 WHERE 子句中明确添加 字段名 IS NOT NULL AND 字段名 != '' 过滤逻辑；
    - 所有参与过滤 / 计算的字段必须是当前查询表 /object 的自有字段
    - 过滤条件中使用的函数 / 语法必须匹配当前 dbType
    - 注意过滤条件 !='' 只有字段类型是字符串类型的时候才添加，其他类型的只添加IS NOT NULL 即可
12. **【多对象结果合并禁令】**：
    当用户问题要求同时返回来自多个不同对象的数据时，必须存在覆盖所有目标对象的显式关联路径（通过 relations 链接）。若各对象之间不存在两两显式关联，即使每个对象都能单独按条件查询，也不得将多个独立查询结果拼接成一个回答。此类请求应视为无法回答，并返回 canAnswer: false + clarification，说明缺少跨对象关联关系。
## 【关联严格约束规则】
1. 所有表之间的关联，**必须来自对象视图元数据中显式声明的 relations**，无声明则绝对不允许 JOIN。
2. 禁止根据字段名相似、业务常识、用户意图脑补关联关系。
3. 禁止仅通过公共字段（如用户ID、工号、编码）隐式关联未声明关系的表。
4. 若查询需要跨表，但表之间无显式 relations → 直接拒答，不生成 SQL。
5. 拒答时必须清晰说明：缺少哪些表之间的显式关联关系。
6. 所有查询计划必须严格基于给定对象视图元数据，不扩展、不假设、不推导。"""

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
            base["term_hint"] = "接受名称或ID或编码，系统会解析"
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
                base["term_hint"] = "接受名称或ID或编码，系统会解析"
        except Exception:
            base["term_type"] = "lookup"
            base["term_hint"] = "接受名称或ID或编码，系统会解析"
    elif term_set:
        base["term_type"] = "lookup"
        base["term_hint"] = "接受名称或ID或编码，系统会解析"
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
            f.pop("description", None)
            if f.get("aliases") == []:
                f.pop("aliases", None)
            base = {k: v for k, v in f.items() if v is not None}
            obj["fields"][i] = _inject_term_info(base, term_loader)
        for act in obj.get("actions", []):
            act.pop("description", None)
            in_serialized = [
                _serialize_param(p, term_loader) for p in act.get("input_params", [])
            ]
            out_serialized = [
                {k: v for k, v in p.items() if v is not None}
                for p in act.get("output_params", [])
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
    """PlanAgent 状态。"""

    payload: ObjectViewPayload
    question: str
    term_loader: Any
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

    async def _generate_node(self, state: PlanAgentState) -> dict[str, Any]:
        """generate 节点：调用 LLM 生成 QueryExecutionPlan。"""
        question = state["question"]
        validation_errors = state.get("validation_errors")

        llm = self._get_llm()

        cached_json = state.get("object_view_json")
        if cached_json is None:
            serialized = _serialize_payload(
                state["payload"], term_loader=state.get("term_loader")
            )
            cached_json = json.dumps(serialized, ensure_ascii=False, separators=(",", ":"))

        user_message = _build_user_message(
            cached_json, question, validation_errors
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        response = await llm.ainvoke(messages)
        content = response.content if hasattr(response, "content") else str(response)
        plan_dict = parse_json_response(str(content))
        data = camel_to_snake_keys(
            plan_dict, preserve_children={"params", "tags"}
        )
        plan = parse_plan(data, question)
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
            "term_loader": term_loader,
            "validation_errors": None,
            "retry_count": 0,
            "plan": None,
            "validation_result": None,
        }
        final = await self._graph.ainvoke(initial)
        plan = final["plan"]
        vr = final.get("validation_result")
        return (plan, vr)

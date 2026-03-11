"""QueryPlanGenerator: LLM 驱动的查询计划生成。"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from datacloud_data_sdk.exceptions import PlanGenerationError
from datacloud_data_sdk.plan.models import (
    ObjectViewPayload,
    PlanAggregation,
    PlanStep,
    QueryExecutionPlan,
)


def camel_to_snake(name: str) -> str:
    """canAnswer -> can_answer, sqlTemplate -> sql_template"""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def snake_to_camel(name: str) -> str:
    """can_answer -> canAnswer, sql_template -> sqlTemplate"""
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def camel_to_snake_keys(
    d: dict | list | object,
    preserve_children: set[str] | None = None,
) -> dict | list | object:
    """递归转换 dict 的 key 从 camelCase 到 snake_case。

    preserve_children: 这些 key 对应的 dict 值不递归转换其子 key，用于 params 等
    需与 param_code 保持一致的字段（param_code 来自 ontology，可能为 camelCase）。
    """
    if isinstance(d, dict):
        result = {}
        for k, v in d.items():
            new_k = camel_to_snake(k)
            if preserve_children and new_k in preserve_children and isinstance(v, dict):
                result[new_k] = v
            else:
                result[new_k] = camel_to_snake_keys(
                    v, preserve_children=preserve_children
                )
        return result
    if isinstance(d, list):
        return [camel_to_snake_keys(i, preserve_children=preserve_children) for i in d]
    return d


def snake_to_camel_keys(d: dict | list | object) -> dict | list | object:
    """递归转换 dict 的 key 从 snake_case 到 camelCase。"""
    if isinstance(d, dict):
        return {snake_to_camel(k): snake_to_camel_keys(v) for k, v in d.items()}
    if isinstance(d, list):
        return [snake_to_camel_keys(i) for i in d]
    return d


SYSTEM_PROMPT = """你是一个严格遵循元数据的数据查询计划生成器，**绝对禁止编造对象视图中不存在的表、字段、动作、条件**。所有SQL、条件、列必须100%来源于给定的 objectView，不允许脑补、推测、新增任何元数据中没有的内容。

根据「对象视图」和「用户问题」，生成一份结构化的查询执行计划（QueryExecutionPlan）。

## 输入
1. **对象视图（objectView）**：sources（API/DB/KB）、objects（字段、表、actions）、relations（对象间关联）。
   - DB 类 object 的 fields 含 **name**（对象属性名）和 **sourceColumn**（数据库物理列名）。
   - **SQL 列名规则**：列/表达式内部必须使用 sourceColumn（物理列名）；**每个 SELECT 输出列必须用 AS 指定别名为 name（对象属性名）**，以便 aggregation 正确取值。示例：`SELECT completed_contract_amount AS completedContractAmount, SUM(x) AS totalX FROM t`。
   - **SQL 条件字段规则**：若DB字段包含 termSet（任意termType）或 termHint（如"接受名称或ID或编码，系统会解析"），该字段可直接在SQL WHERE条件中填写用户问题中的名称/文本值，**无需先调用API获取ID/编码**，系统会在执行时自动解析。

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
{"stepId":"s1","type":"SQL","datasourceAlias":"crm_db","sqlTemplate":"SELECT ...","outputRef":"out","csvTableName":"","bindFromStep":"","bindKey":""}
```
- stepId: 必填；type: "SQL"；datasourceAlias: 数据源别名；sqlTemplate: SQL 语句；outputRef: 输出引用；csvTableName、bindFromStep、bindKey 可选。
- **sqlTemplate 列名规则**：1）列/函数/表达式内部必须使用 sourceColumn（物理列名），禁止使用 name；2）**每个输出列必须写 AS <name>**，name 为对象字段名（field_code），与 aggregation.columns[].name 一致。简单列、聚合函数、CASE 等均需 AS。示例：`SELECT completed_contract_amount AS completedContractAmount, SUM(completed_contract_amount) AS totalAmount FROM t`。

**type:"API"**（仅允许以下字段）：
```json
{"stepId":"s1","type":"API","objectId":"sales_emp","functionId":"query_emp","params":{"names":["张三"]},"outputRef":"out","csvTableName":"api_emp","bindFromStep":"","bindKey":""}
```
- stepId: 必填；type: "API"；objectId: 必填，从 objectView.objects 选取；functionId: 必填，= actionCode，从该 object 的 actions 选取；params: 入参，key 为 action 的 paramCode；outputRef: 必填；csvTableName: 跨数据源时必填；bindFromStep、bindKey 可选。

**type:"KB"**（仅允许以下字段）：
```json
{"stepId":"s1","type":"KB","datasourceAlias":"kb_ds","query":"用户问题关键词","tags":{"belong_emp_no":"xxx"},"outputRef":"kb_out"}
```
- stepId: 必填；type: "KB"；datasourceAlias: 数据源别名；query: 检索文本；tags: 可选；outputRef: 必填。

### 其他输出要求

- **canAnswer**（必填）：
  - 只有**所有查询条件、过滤字段、返回列都能在对象视图中找到**时，才为 true；
  - 只要缺少必要表、字段、API，或需要使用视图中**不存在的字段/条件**才能回答，一律为 false。

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
    - 跨数据源查询（API+DB/不同DB）：仅当SQL无法独立完成查询（必须依赖API数据）时，才为每个数据源生成数据导出步骤（API步骤/DB查询步骤），标记csvTableName（CSV表名），**禁止生成额外的SQLITE_MEM类型步骤**；各步骤的临时表（csvTableName）**仅允许在aggregation阶段使用**，步骤间禁止相互引用对方的输出结果表。
    - **API 步骤**：type:"API"，stepId, objectId, functionId（对应 actionCode）, params（入参，key 为 paramCode）, outputRef, csvTableName（跨数据源时必填）。若需从前序步骤取列值，增加 bindFromStep、bindKey。**仅当SQL无法独立完成查询时才允许生成API步骤**，禁止为可通过SQL直接查询的场景新增API步骤。
    - 知识库检索：当 objectView 的 sources 中含 source_type 为 KNOWLEDGE_BASE 时，可生成 type:"KB" 步骤。KB 步骤需包含：stepId, type:"KB", datasourceAlias（数据源别名）, query（检索文本）, tags（可选，dict，field_code->value，用于按对象属性过滤）, outputRef。示例：{"stepId":"s1","type":"KB","datasourceAlias":"kb_ds","query":"用户问题关键词","tags":{"belong_emp_no":"xxx"},"outputRef":"kb_out"}
  - **aggregation**（必填）：最终结果聚合规则，**仅该阶段可使用steps中各步骤的临时表（csvTableName）**。
    - strategy：
      - "DIRECT"：结果直接来自某条SQL（包括同数据源多表关联的SQL），无跨数据源计算。
      - "SQLITE_MEM"：跨数据源/API+DB 关联，基于各数据源导出步骤的CSV结果，在SQLite内存数据库中执行关联查询。
    - "DIRECT" 必须包含 finalStepId（指向唯一的SQL步骤ID）。
    - "SQLITE_MEM" 仅需包含 sqliteSql（基于steps中各CSV表名的SQLite关联查询语句），**禁止输出csvTables字段**。
    - columns：数组，每一项 {name, label, type}，**name 必须与 sqlTemplate 中对应列的 AS 别名完全一致**（即对象字段名），label/type 来自视图字段描述。
  - 禁止输出 clarification 字段，禁止输出除 canAnswer、steps、aggregation 外的任何多余字段。

## 铁律约束（必须严格遵守）
1. **严禁编造**：不允许使用对象视图中**不存在的表名、字段名、动作**，不允许凭空增加时间字段、状态字段、过滤条件。
2. 单表/同数据源多表查询：steps 仅输出 1 条SQL，多表关联直接在该SQL中通过JOIN实现，**禁止拆分多步**；aggregation 使用 strategy=DIRECT。
3. 跨数据源/多数据源关联：必须使用 strategy=SQLITE_MEM；steps 仅包含各数据源的导出步骤，**步骤间禁止引用彼此的输出结果表**，仅aggregation阶段可使用各步骤的临时表；aggregation 中禁止输出csvTables字段，仅保留sqliteSql。
4. 禁止空步骤 steps=[] 且 finalStepId=null。
5. 核心要求：能单步SQL完成的查询**必须仅生成1条SQL步骤**，禁止拆分为多步；steps中的临时表仅允许在aggregation阶段使用，步骤内禁止引用其他步骤的输出表；**可通过SQL独立完成的查询，禁止生成任何API步骤**，杜绝冗余的API+SQL两步执行的情况。
6. 输出的JSON中仅包含约定的字段，禁止出现任何未约定的多余字段。
7. **SQL 与 aggregation 对齐**：sqlTemplate 中每个 SELECT 列必须 `AS <对象字段名>`；aggregation.columns[].name 必须与这些 AS 别名一致，否则 DirectAggregator 无法正确输出。
8. aggregation.columns 强制约束：aggregation.columns 是必填字段，必须为非空数组，数组内每个元素必须完整包含 name、label、type 三个字段，且字段值均不能为空，必须严格匹配对象视图中的元数据。
9. 步骤间隔离约束：steps 中所有类型步骤（SQL/API/KB）的逻辑（包括 SQL 的表 / 条件、API 的入参）仅允许基于 objectView 的原始元数据，禁止引用任何其他步骤的输出结果、临时表（csvTableName）、outputRef；所有跨步骤的关联 / 条件过滤逻辑仅允许在 aggregation 阶段通过 sqliteSql 实现。
10. SQL 条件字段专属约束：若 DB 字段包含 termSet（任意 termType）或 termHint，直接在 SQL WHERE 条件中填写用户问题中的名称 / 文本值，禁止通过 API 步骤 / 子查询获取该字段的 ID / 编码，禁止为该场景生成任何前置 API 步骤。"""

RETRY_PROMPT_TEMPLATE = """上次生成的计划校验失败，原因如下：
{validation_errors}
请根据上述错误修正计划并重新输出完整的 QueryExecutionPlan JSON。"""


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
    """
    raw = asdict(payload)
    objects = raw.get("objects", [])
    for obj in objects:
        # 移除 functions，仅保留 actions
        if "functions" in obj:
            del obj["functions"]
        # fields 中仅当 source_column 非空时保留，供 LLM 在 SQL 中使用物理列名；注入 term 信息
        for i, f in enumerate(obj.get("fields", [])):
            if not f.get("source_column"):
                f.pop("source_column", None)
            base = {k: v for k, v in f.items() if v is not None}
            obj["fields"][i] = _inject_term_info(base, term_loader)
        for act in obj.get("actions", []):
            in_serialized = [
                _serialize_param(p, term_loader) for p in act.get("input_params", [])
            ]
            out_serialized = [
                {k: v for k, v in p.items() if v is not None}
                for p in act.get("output_params", [])
            ]
            act["input_params"] = in_serialized
            act["output_params"] = out_serialized
    return snake_to_camel_keys(raw)  # type: ignore[return-value]


def _serialize_param(p: dict[str, Any], term_loader: Any) -> dict[str, Any]:
    """序列化单个入参，注入 termType/termLabels/termHint。优先使用 param 的 term_type。"""
    base = {k: v for k, v in p.items() if v is not None}
    return _inject_term_info(base, term_loader)


class BasePlanGenerator(ABC):
    @abstractmethod
    async def generate(
        self,
        payload: ObjectViewPayload,
        question: str,
        validation_errors: list[str] | None = None,
        term_loader: Any = None,
    ) -> QueryExecutionPlan:
        ...


class MockPlanGenerator(BasePlanGenerator):
    """Mock 计划生成器，直接返回固定计划，用于测试。"""

    def __init__(self, fixed_plan: dict[str, Any]) -> None:
        self._plan = fixed_plan

    async def generate(
        self,
        payload: ObjectViewPayload,
        question: str,
        validation_errors: list[str] | None = None,
        term_loader: Any = None,
    ) -> QueryExecutionPlan:
        data = camel_to_snake_keys(self._plan)
        return _parse_plan(data, question)  # type: ignore[arg-type]


class LangGraphPlanGenerator(BasePlanGenerator):
    """基于 LLM 的查询计划生成器。

    使用 langchain-openai 调用兼容 OpenAI 的 LLM，
    将 ObjectViewPayload + 用户问题组装为 Prompt，解析返回的 JSON 为 QueryExecutionPlan。
    支持校验失败后重试（最多 max_retries 次）。
    """

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

    async def generate(
        self,
        payload: ObjectViewPayload,
        question: str,
        validation_errors: list[str] | None = None,
        term_loader: Any = None,
    ) -> QueryExecutionPlan:
        """调用 LLM 生成查询计划。"""
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise PlanGenerationError(
                question,
                "langchain-openai not installed. Install with: pip install langchain-openai",
            ) from e

        llm = ChatOpenAI(
            model=self._model,
            base_url=self._base_url,
            api_key=self._api_key,
            temperature=self._temperature,
        )

        object_view_json = json.dumps(
            _serialize_payload(payload, term_loader=term_loader),
            ensure_ascii=False,
            indent=2,
        )

        user_message = self._build_user_message(object_view_json, question, validation_errors)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await llm.ainvoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            plan_dict = self._parse_json_response(str(content))
            data = camel_to_snake_keys(
                plan_dict, preserve_children={"params", "tags"}
            )
            return _parse_plan(data, question)  # type: ignore[arg-type]
        except PlanGenerationError:
            raise
        except Exception as e:
            raise PlanGenerationError(question, str(e)) from e

    def _build_user_message(
        self,
        object_view_json: str,
        question: str,
        validation_errors: list[str] | None = None,
    ) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"## 当前时间：\n{now}\n"]

        if validation_errors:
            errors_text = "\n".join(f"- {e}" for e in validation_errors)
            parts.append(RETRY_PROMPT_TEMPLATE.format(validation_errors=errors_text))

        parts.append(f"## 输入内容\n\n**对象视图：**\n{object_view_json}")
        parts.append(f"\n**用户问题：**\n{question}")
        parts.append("\n请直接输出 QueryExecutionPlan 的 JSON，不要输出其他内容。")
        return "\n".join(parts)

    def _parse_json_response(self, content: str) -> dict[str, Any]:
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
            raise PlanGenerationError("", f"Failed to parse LLM JSON response: {e}\nContent: {content[:500]}")


def _parse_plan(data: dict[str, Any], question: str = "") -> QueryExecutionPlan:
    """将 snake_case dict 解析为 QueryExecutionPlan。"""
    steps = [
        PlanStep(**{k: v for k, v in s.items() if k in PlanStep.__dataclass_fields__})
        for s in data.get("steps", [])
    ]
    agg_data = data.get("aggregation")
    aggregation = None
    if agg_data:
        aggregation = PlanAggregation(
            **{k: v for k, v in agg_data.items() if k in PlanAggregation.__dataclass_fields__}
        )
    return QueryExecutionPlan(
        question=data.get("question", question),
        can_answer=data.get("can_answer", True),
        clarification=data.get("clarification", ""),
        steps=steps,
        aggregation=aggregation,
    )

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


def camel_to_snake_keys(d: dict | list | object) -> dict | list | object:
    """递归转换 dict 的 key 从 camelCase 到 snake_case。"""
    if isinstance(d, dict):
        return {camel_to_snake(k): camel_to_snake_keys(v) for k, v in d.items()}
    if isinstance(d, list):
        return [camel_to_snake_keys(i) for i in d]
    return d


def snake_to_camel_keys(d: dict | list | object) -> dict | list | object:
    """递归转换 dict 的 key 从 snake_case 到 camelCase。"""
    if isinstance(d, dict):
        return {snake_to_camel(k): snake_to_camel_keys(v) for k, v in d.items()}
    if isinstance(d, list):
        return [snake_to_camel_keys(i) for i in d]
    return d


SYSTEM_PROMPT = """你是一个严格遵循元数据的数据查询计划生成器，**绝对禁止编造对象视图中不存在的表、字段、函数、条件**。所有SQL、条件、列必须100%来源于给定的 objectView，不允许脑补、推测、新增任何元数据中没有的内容。

根据「对象视图」和「用户问题」，生成一份结构化的查询执行计划（QueryExecutionPlan）。

## 输入
1. **对象视图（objectView）**：描述当前可用的数据源与对象能力，包括 sources（API/DB）、objects（字段与函数/表）、relations（对象间关联与 joinKeys）。
2. **用户问题（question）**：用户的自然语言查询。

## 输出要求
请**仅输出一份合法的 JSON**，即 QueryExecutionPlan，不要包含其他解释或 markdown 代码块标记。结构约定如下：

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
    - 单DB表查询：生成 1 条 type:"SQL" 步骤，**只使用视图中已声明的表和字段**。
    - 同数据源多表关联查询（如同一DB下的多张表JOIN）：仅生成 1 条 type:"SQL" 步骤，直接在SQL中完成多表关联，**禁止拆分为多条SQL步骤**。
    - 跨数据源查询（API+DB/不同DB）：仅为每个数据源生成数据导出步骤（API步骤/DB查询步骤），标记csvTableName（CSV表名），**禁止生成额外的SQLITE_MEM类型步骤**。
    - 知识库检索：当 objectView 的 sources 中含 source_type 为 KNOWLEDGE_BASE 时，可生成 type:"KB" 步骤。KB 步骤需包含：stepId, type:"KB", datasourceAlias（数据源别名）, query（检索文本）, tags（可选，dict，field_code->value，用于按对象属性过滤）, outputRef。示例：{"stepId":"s1","type":"KB","datasourceAlias":"kb_ds","query":"用户问题关键词","tags":{"belong_emp_no":"xxx"},"outputRef":"kb_out"}
  - **aggregation**（必填）：最终结果聚合规则。
    - strategy：
      - "DIRECT"：结果直接来自某条SQL（包括同数据源多表关联的SQL），无跨数据源计算。
      - "SQLITE_MEM"：跨数据源/API+DB 关联，基于各数据源导出步骤的CSV结果，在SQLite内存数据库中执行关联查询。
    - "DIRECT" 必须包含 finalStepId（指向唯一的SQL步骤ID）。
    - "SQLITE_MEM" 仅需包含 sqliteSql（基于steps中各CSV表名的SQLite关联查询语句），**禁止输出csvTables字段**。
    - columns：数组，每一项 {name, label, type}，**列必须来自视图已有字段**。
  - 禁止输出 clarification 字段，禁止输出除 canAnswer、steps、aggregation 外的任何多余字段。

## 铁律约束（必须严格遵守）
1. **严禁编造**：不允许使用对象视图中**不存在的表名、字段名、函数**，不允许凭空增加时间字段、状态字段、过滤条件。
2. 单表/同数据源多表查询：steps 仅输出 1 条SQL，多表关联直接在该SQL中通过JOIN实现。aggregation 使用 strategy=DIRECT。
3. 跨数据源/多数据源关联：必须使用 strategy=SQLITE_MEM。steps 仅包含各数据源的导出步骤。aggregation 中禁止输出csvTables字段，仅保留sqliteSql。
4. 禁止空步骤 steps=[] 且 finalStepId=null。
5. 禁止将同数据源的多表关联查询拆分为多条SQL步骤。
6. 输出的JSON中仅包含约定的字段，禁止出现任何未约定的多余字段。"""

RETRY_PROMPT_TEMPLATE = """上次生成的计划校验失败，原因如下：
{validation_errors}
请根据上述错误修正计划并重新输出完整的 QueryExecutionPlan JSON。"""


def _serialize_payload(payload: ObjectViewPayload) -> dict[str, Any]:
    """将 ObjectViewPayload 序列化为 camelCase JSON 供 LLM 消费。"""
    raw = asdict(payload)
    return snake_to_camel_keys(raw)  # type: ignore[return-value]


class BasePlanGenerator(ABC):
    @abstractmethod
    async def generate(self, payload: ObjectViewPayload, question: str) -> QueryExecutionPlan:
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
            _serialize_payload(payload), ensure_ascii=False, indent=2
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
            data = camel_to_snake_keys(plan_dict)
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

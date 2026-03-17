"""PlanAgent 单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from datacloud_data.agents.plan_agent import PlanAgent
from datacloud_data.plan.models import (
    ObjectViewPayload,
    ObjectViewSource,
    PlanAggregation,
    PlanStep,
    QueryExecutionPlan,
)

PAYLOAD = ObjectViewPayload(view_id="v1", sources=[], objects=[], relations=[])

# validate 节点测试用：带有效 source 的 payload
PAYLOAD_WITH_SOURCE = ObjectViewPayload(
    view_id="v1",
    sources=[
        ObjectViewSource(
            source_id="SRC_CRM",
            source_type="DB",
            datasource_alias="crm_db",
            db_type="POSTGRESQL",
        )
    ],
    objects=[],
    relations=[],
)

# canAnswer=true 的固定 JSON 响应
MOCK_LLM_RESPONSE_JSON = """{"canAnswer":true,"question":"查商机","steps":[{"stepId":"s1","type":"SQL","sourceId":"SRC","datasourceAlias":"crm_db","sqlTemplate":"SELECT 1","outputRef":"result"}],"aggregation":{"strategy":"DIRECT","finalStepId":"s1","columns":[{"name":"x","label":"X","type":"string"}]}}"""


@pytest.mark.asyncio
async def test_generate_node_returns_plan() -> None:
    """Mock ChatOpenAI.ainvoke 返回固定 JSON，验证 _generate_node 返回正确的 plan。"""
    with patch("langchain_openai.ChatOpenAI") as mock_chat_cls:
        mock_instance = MagicMock()
        mock_instance.ainvoke = AsyncMock(
            return_value=MagicMock(content=MOCK_LLM_RESPONSE_JSON)
        )
        mock_chat_cls.return_value = mock_instance

        agent = PlanAgent()
        state: dict = {
            "payload": PAYLOAD,
            "question": "查商机",
            "validation_errors": None,
        }

        result = await agent._generate_node(state)

        assert "plan" in result
        plan = result["plan"]
        assert isinstance(plan, QueryExecutionPlan)
        assert plan.can_answer is True
        assert plan.question == "查商机"
        assert len(plan.steps) == 1
        assert plan.steps[0].step_id == "s1"
        assert plan.steps[0].type == "SQL"
        assert plan.steps[0].sql_template == "SELECT 1"
        assert plan.aggregation is not None
        assert plan.aggregation.strategy == "DIRECT"
        assert plan.aggregation.final_step_id == "s1"


@pytest.mark.asyncio
async def test_generate_node_with_validation_errors_includes_retry_prompt() -> None:
    """当 validation_errors 非空时，user message 应包含 RETRY_PROMPT_TEMPLATE 内容。"""
    captured_messages = []

    async def capture_ainvoke(messages):
        captured_messages.append(messages)
        return MagicMock(content=MOCK_LLM_RESPONSE_JSON)

    with patch("langchain_openai.ChatOpenAI") as mock_chat_cls:
        mock_instance = MagicMock()
        mock_instance.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_chat_cls.return_value = mock_instance

        agent = PlanAgent()
        state: dict = {
            "payload": PAYLOAD,
            "question": "查商机",
            "validation_errors": ["错误1：SQL 语法不正确", "错误2：缺少必要字段"],
        }

        result = await agent._generate_node(state)

        assert "plan" in result
        assert len(captured_messages) == 1
        user_content = captured_messages[0][1]["content"]
        # 应包含 RETRY_PROMPT_TEMPLATE 中的关键词
        assert "校验失败" in user_content or "错误" in user_content
        assert "错误1" in user_content
        assert "错误2" in user_content


def test_validate_node_can_answer_false_returns_none() -> None:
    """can_answer=False 时，_validate_node 不校验，返回 validation_result=None。"""
    agent = PlanAgent()
    plan = QueryExecutionPlan(
        question="查商机",
        can_answer=False,
        clarification="需要更多信息",
        steps=[],
        aggregation=None,
    )
    state = {"plan": plan, "payload": PAYLOAD}
    result = agent._validate_node(state)
    assert result["validation_result"] is None
    assert "validation_errors" not in result
    assert "retry_count" not in result


def test_validate_node_valid_plan_returns_valid_result() -> None:
    """合法计划校验通过，返回 validation_result.valid=True。"""
    agent = PlanAgent()
    plan = QueryExecutionPlan(
        question="查商机",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="SQL",
                source_id="SRC_CRM",
                datasource_alias="crm_db",
                sql_template="SELECT 1",
                output_ref="result",
            )
        ],
        aggregation=PlanAggregation(
            strategy="DIRECT",
            final_step_id="s1",
            columns=[{"name": "x", "label": "X", "type": "string"}],
        ),
    )
    state = {"plan": plan, "payload": PAYLOAD_WITH_SOURCE}
    result = agent._validate_node(state)
    assert result["validation_result"] is not None
    assert result["validation_result"].valid is True
    assert result["validation_result"].errors == []
    assert "validation_errors" not in result
    assert "retry_count" not in result


def test_validate_node_invalid_plan_updates_errors_and_retry_count() -> None:
    """非法计划校验失败时，更新 validation_errors 和 retry_count。"""
    agent = PlanAgent()
    plan = QueryExecutionPlan(
        question="查商机",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="SQL",
                source_id="NONEXISTENT",
                output_ref="x",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    state = {"plan": plan, "payload": PAYLOAD_WITH_SOURCE, "retry_count": 0}
    result = agent._validate_node(state)
    assert result["validation_result"] is not None
    assert result["validation_result"].valid is False
    assert len(result["validation_result"].errors) > 0
    assert result["validation_errors"] == result["validation_result"].errors
    assert result["retry_count"] == 1


def test_route_after_validate_can_answer_false_returns_end() -> None:
    """can_answer=False 时路由到 __end__。"""
    agent = PlanAgent()
    plan = QueryExecutionPlan(
        question="x", can_answer=False, clarification="x", steps=[], aggregation=None
    )
    state = {"plan": plan, "validation_result": None}
    assert agent._route_after_validate(state) == "__end__"


def test_route_after_validate_valid_returns_end() -> None:
    """校验通过时路由到 __end__。"""
    from datacloud_data.plan.plan_validator import ValidationResult

    agent = PlanAgent()
    plan = QueryExecutionPlan(
        question="x", can_answer=True, steps=[], aggregation=None
    )
    state = {"plan": plan, "validation_result": ValidationResult(valid=True, errors=[])}
    assert agent._route_after_validate(state) == "__end__"


def test_route_after_validate_invalid_with_retries_returns_generate() -> None:
    """校验失败且 retry_count < max_retries 时路由到 generate。"""
    from datacloud_data.plan.plan_validator import ValidationResult

    agent = PlanAgent(max_retries=2)
    plan = QueryExecutionPlan(
        question="x", can_answer=True, steps=[], aggregation=None
    )
    state = {
        "plan": plan,
        "validation_result": ValidationResult(valid=False, errors=["err"]),
        "retry_count": 1,
    }
    assert agent._route_after_validate(state) == "generate"


def test_route_after_validate_invalid_exhausted_returns_end() -> None:
    """校验失败且 retry_count > max_retries 时路由到 __end__（已耗尽重试）。"""
    from datacloud_data.plan.plan_validator import ValidationResult

    agent = PlanAgent(max_retries=2)
    plan = QueryExecutionPlan(
        question="x", can_answer=True, steps=[], aggregation=None
    )
    state = {
        "plan": plan,
        "validation_result": ValidationResult(valid=False, errors=["err"]),
        "retry_count": 3,  # 已失败 3 次，超过 max_retries=2
    }
    assert agent._route_after_validate(state) == "__end__"


# --- run() 集成测试 ---

# canAnswer=false 的固定 JSON 响应
MOCK_LLM_RESPONSE_CANNOT_ANSWER = """{"canAnswer":false,"clarification":"需要更多信息","question":"查商机","steps":[],"aggregation":null}"""

# 合法计划：sourceId 与 PAYLOAD_WITH_SOURCE 的 SRC_CRM 匹配
MOCK_LLM_RESPONSE_VALID = """{"canAnswer":true,"question":"查商机","steps":[{"stepId":"s1","type":"SQL","sourceId":"SRC_CRM","datasourceAlias":"crm_db","sqlTemplate":"SELECT 1","outputRef":"result"}],"aggregation":{"strategy":"DIRECT","finalStepId":"s1","columns":[{"name":"x","label":"X","type":"string"}]}}"""

# 非法计划：source_id 不存在于 payload
MOCK_LLM_RESPONSE_INVALID = """{"canAnswer":true,"question":"查商机","steps":[{"stepId":"s1","type":"SQL","sourceId":"NONEXISTENT","datasourceAlias":"crm_db","sqlTemplate":"SELECT 1","outputRef":"result"}],"aggregation":{"strategy":"DIRECT","finalStepId":"s1","columns":[{"name":"x","label":"X","type":"string"}]}}"""


@pytest.mark.asyncio
async def test_run_can_answer_false_returns_plan_and_none() -> None:
    """Mock LLM 返回 canAnswer=false，验证 run 返回 (plan, None)，plan.can_answer=False。"""
    with patch("langchain_openai.ChatOpenAI") as mock_chat_cls:
        mock_instance = MagicMock()
        mock_instance.ainvoke = AsyncMock(
            return_value=MagicMock(content=MOCK_LLM_RESPONSE_CANNOT_ANSWER)
        )
        mock_chat_cls.return_value = mock_instance

        agent = PlanAgent()
        plan, vr = await agent.run(PAYLOAD, "查商机")

        assert plan is not None
        assert plan.can_answer is False
        assert plan.clarification == "需要更多信息"
        assert vr is None


@pytest.mark.asyncio
async def test_run_valid_returns_plan_and_valid_result() -> None:
    """Mock LLM 返回合法计划，验证 run 返回 (plan, vr)，vr.valid=True。"""
    with patch("langchain_openai.ChatOpenAI") as mock_chat_cls:
        mock_instance = MagicMock()
        mock_instance.ainvoke = AsyncMock(
            return_value=MagicMock(content=MOCK_LLM_RESPONSE_VALID)
        )
        mock_chat_cls.return_value = mock_instance

        agent = PlanAgent()
        plan, vr = await agent.run(PAYLOAD_WITH_SOURCE, "查商机")

        assert plan is not None
        assert plan.can_answer is True
        assert vr is not None
        assert vr.valid is True
        assert vr.errors == []


@pytest.mark.asyncio
async def test_run_invalid_returns_plan_and_invalid_result() -> None:
    """Mock LLM 返回非法计划，验证 run 返回 (plan, vr)，vr.valid=False。"""
    with patch("langchain_openai.ChatOpenAI") as mock_chat_cls:
        mock_instance = MagicMock()
        mock_instance.ainvoke = AsyncMock(
            return_value=MagicMock(content=MOCK_LLM_RESPONSE_INVALID)
        )
        mock_chat_cls.return_value = mock_instance

        agent = PlanAgent(max_retries=0)
        plan, vr = await agent.run(PAYLOAD_WITH_SOURCE, "查商机")

        assert plan is not None
        assert plan.can_answer is True
        assert vr is not None
        assert vr.valid is False
        assert len(vr.errors) > 0


@pytest.mark.asyncio
async def test_run_retry_then_pass() -> None:
    """Mock LLM 第一次返回非法计划、第二次合法，验证重试后成功。"""
    call_count = 0

    async def side_effect(_):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock(content=MOCK_LLM_RESPONSE_INVALID)
        return MagicMock(content=MOCK_LLM_RESPONSE_VALID)

    with patch("langchain_openai.ChatOpenAI") as mock_chat_cls:
        mock_instance = MagicMock()
        mock_instance.ainvoke = AsyncMock(side_effect=side_effect)
        mock_chat_cls.return_value = mock_instance

        agent = PlanAgent(max_retries=2)
        plan, vr = await agent.run(PAYLOAD_WITH_SOURCE, "查商机")

        assert call_count == 2
        assert plan is not None
        assert plan.can_answer is True
        assert vr is not None
        assert vr.valid is True


@pytest.mark.asyncio
async def test_run_retry_exhausted() -> None:
    """Mock LLM 始终返回非法计划，max_retries=1，验证 run 返回 (plan, vr)，vr.valid=False。"""
    with patch("langchain_openai.ChatOpenAI") as mock_chat_cls:
        mock_instance = MagicMock()
        mock_instance.ainvoke = AsyncMock(
            return_value=MagicMock(content=MOCK_LLM_RESPONSE_INVALID)
        )
        mock_chat_cls.return_value = mock_instance

        agent = PlanAgent(max_retries=1)
        plan, vr = await agent.run(PAYLOAD_WITH_SOURCE, "查商机")

        assert plan is not None
        assert plan.can_answer is True
        assert vr is not None
        assert vr.valid is False
        assert len(vr.errors) > 0

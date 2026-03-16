import pytest
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.models import (
    ObjectViewAction,
    ObjectViewField,
    ObjectViewFunction,
    ObjectViewFunctionParam,
    ObjectViewObject,
    ObjectViewPayload,
    ObjectViewSource,
    QueryExecutionPlan,
)
from datacloud_data_sdk.plan.query_plan_generator import (
    BasePlanGenerator,
    MockPlanGenerator,
    _serialize_payload,
)
from datacloud_data_sdk.utils.case_utils import camel_to_snake, camel_to_snake_keys

PAYLOAD = ObjectViewPayload(view_id="v1", sources=[], objects=[], relations=[])

MOCK_PLAN = {
    "question": "查商机",
    "can_answer": True,
    "steps": [{"step_id": "s1", "type": "SQL", "source_id": "SRC_CRM",
               "datasource_alias": "crm_db", "sql_template": "SELECT 1",
               "output_ref": "result"}],
    "aggregation": {"strategy": "DIRECT", "final_step_id": "s1", "columns": []},
}


@pytest.mark.asyncio
async def test_mock_plan_generator_returns_plan() -> None:
    gen = MockPlanGenerator(fixed_plan=MOCK_PLAN)
    plan = await gen.generate(PAYLOAD, "查商机")
    assert isinstance(plan, QueryExecutionPlan)
    assert plan.can_answer is True


@pytest.mark.asyncio
async def test_mock_plan_generator_cannot_answer() -> None:
    gen = MockPlanGenerator(fixed_plan={"question": "？", "can_answer": False,
                                         "clarification": "无法回答"})
    plan = await gen.generate(PAYLOAD, "？")
    assert plan.can_answer is False
    assert plan.clarification == "无法回答"


def test_camel_to_snake() -> None:
    assert camel_to_snake("canAnswer") == "can_answer"
    assert camel_to_snake("sqlTemplate") == "sql_template"
    assert camel_to_snake("finalStepId") == "final_step_id"
    assert camel_to_snake("step_id") == "step_id"


def test_camel_to_snake_keys() -> None:
    data = {"canAnswer": True, "steps": [{"stepId": "s1", "sqlTemplate": "SELECT 1"}]}
    result = camel_to_snake_keys(data)
    assert "can_answer" in result
    assert result["steps"][0]["step_id"] == "s1"
    assert result["steps"][0]["sql_template"] == "SELECT 1"


@pytest.mark.asyncio
async def test_camel_case_plan_parsed_correctly() -> None:
    camel_plan = {
        "question": "test",
        "canAnswer": True,
        "steps": [{"stepId": "s1", "type": "SQL", "sourceId": "SRC",
                    "datasourceAlias": "db", "sqlTemplate": "SELECT 1",
                    "outputRef": "r"}],
        "aggregation": {"strategy": "DIRECT", "finalStepId": "s1", "columns": []},
    }
    gen = MockPlanGenerator(fixed_plan=camel_plan)
    plan = await gen.generate(PAYLOAD, "test")
    assert plan.can_answer is True
    assert plan.steps[0].step_id == "s1"
    assert plan.steps[0].sql_template == "SELECT 1"


@pytest.mark.asyncio
async def test_kb_step_parsed_correctly() -> None:
    """KB 步骤的 query、tags 能被 _parse_plan 正确解析。"""
    kb_plan = {
        "question": "知识库检索",
        "canAnswer": True,
        "steps": [
            {
                "stepId": "s1",
                "type": "KB",
                "datasourceAlias": "kb_ds",
                "query": "用户问题关键词",
                "tags": {"belong_emp_no": "xxx"},
                "outputRef": "kb_out",
            }
        ],
        "aggregation": {"strategy": "DIRECT", "finalStepId": "s1", "columns": []},
    }
    gen = MockPlanGenerator(fixed_plan=kb_plan)
    plan = await gen.generate(PAYLOAD, "知识库检索")
    assert plan.can_answer is True
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.step_id == "s1"
    assert step.type == "KB"
    assert step.datasource_alias == "kb_ds"
    assert step.query == "用户问题关键词"
    assert step.tags == {"belong_emp_no": "xxx"}
    assert step.output_ref == "kb_out"


def test_serialize_payload_splits_input_output_params() -> None:
    """序列化时 action 的 input_params/output_params 转为 inputParams/outputParams，且不输出 functions。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC", source_type="API")],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="对象",
                source_id="SRC",
                functions=[],
                actions=[
                    ObjectViewAction(
                        action_code="act_x",
                        implementation_type="API",
                        input_params=[
                            ObjectViewFunctionParam(
                                "p1", "入参1", "STRING", "IN", term_set="status.code"
                            ),
                        ],
                        output_params=[
                            ObjectViewFunctionParam("p2", "出参2", "STRING", "OUT"),
                        ],
                    )
                ],
            )
        ],
        relations=[],
    )
    result = _serialize_payload(payload)
    obj = result["objects"][0]
    assert "functions" not in obj
    act = obj["actions"][0]
    assert "inputParams" in act
    assert "outputParams" in act
    assert len(act["inputParams"]) == 1
    assert act["inputParams"][0]["paramCode"] == "p1"
    assert len(act["outputParams"]) == 1
    assert act["outputParams"][0]["paramCode"] == "p2"


def test_serialize_payload_fields_include_source_column_when_present() -> None:
    """fields 序列化时，有 source_column 的 field 输出 sourceColumn，无则不出。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC", source_type="DB", datasource_alias="db1")],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="对象",
                source_id="SRC",
                table="t1",
                fields=[
                    ObjectViewField(name="id", type="string", description="ID"),
                    ObjectViewField(
                        name="userId",
                        type="string",
                        description="用户ID",
                        source_column="user_id",
                    ),
                ],
                functions=[],
                actions=[],
            )
        ],
        relations=[],
    )
    result = _serialize_payload(payload)
    fields = result["objects"][0]["fields"]
    id_field = next(f for f in fields if f["name"] == "id")
    user_field = next(f for f in fields if f["name"] == "userId")
    assert "sourceColumn" not in id_field
    assert user_field["sourceColumn"] == "user_id"


def test_serialize_payload_injects_term_labels_with_loader() -> None:
    """有 term_loader 且 term_set 有数据时，对 action 的 inputParams 注入 termType 和 termLabels。"""
    loader = TermLoader.from_mapping({
        "status.code": [{"code": "TODO", "label": "待办"}, {"code": "DONE", "label": "已完成"}],
    })
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="对象",
                source_id="SRC",
                functions=[],
                actions=[
                    ObjectViewAction(
                        action_code="act_x",
                        implementation_type="API",
                        input_params=[
                            ObjectViewFunctionParam(
                                "status", "状态", "STRING", "IN", term_set="status.code"
                            ),
                        ],
                    )
                ],
            )
        ],
        relations=[],
    )
    result = _serialize_payload(payload, term_loader=loader)
    inp = result["objects"][0]["actions"][0]["inputParams"][0]
    assert inp["termType"] == "enum"
    assert inp["termLabels"] == ["待办", "已完成"]


def test_serialize_payload_injects_term_labels_for_fields() -> None:
    """有 term_loader 且 field 有 term_set 时，fields 注入 termType 和 termLabels。"""
    loader = TermLoader.from_mapping({
        "status.code": [{"code": "TODO", "label": "待办"}, {"code": "DONE", "label": "已完成"}],
    })
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="对象",
                source_id="SRC",
                table="t1",
                fields=[
                    ObjectViewField(name="id", type="string", description="ID"),
                    ObjectViewField(
                        name="status",
                        type="string",
                        description="状态",
                        term_set="status.code",
                        source_column="status_code",
                    ),
                ],
                functions=[],
                actions=[],
            )
        ],
        relations=[],
    )
    result = _serialize_payload(payload, term_loader=loader)
    fields = result["objects"][0]["fields"]
    status_field = next(f for f in fields if f["name"] == "status")
    assert status_field["termType"] == "enum"
    assert status_field["termLabels"] == ["待办", "已完成"]


def test_serialize_payload_injects_term_hint_for_lookup_field() -> None:
    """field 有 term_set 且 term_type=lookup 时，注入 termHint。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="对象",
                source_id="SRC",
                fields=[
                    ObjectViewField(
                        name="orgId",
                        type="string",
                        description="组织",
                        term_set="org.code",
                        term_type="lookup",
                        source_column="org_id",
                    ),
                ],
                functions=[],
                actions=[],
            )
        ],
        relations=[],
    )
    result = _serialize_payload(payload)
    org_field = result["objects"][0]["fields"][0]
    assert org_field["termType"] == "lookup"
    assert "termHint" in org_field


def test_serialize_payload_db_source_includes_db_type() -> None:
    """DB 类 source 序列化后包含 dbType。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[
            ObjectViewSource(
                source_id="SRC_CRM",
                source_type="DB",
                datasource_alias="ds_crm",
                db_type="POSTGRESQL",
            )
        ],
        objects=[],
        relations=[],
    )
    result = _serialize_payload(payload)
    sources = result.get("sources", [])
    assert len(sources) == 1
    assert sources[0].get("dbType") == "POSTGRESQL"


def test_serialize_payload_api_source_omits_empty_db_type() -> None:
    """API 类 source 的 db_type 为空时，序列化结果不包含 dbType。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[
            ObjectViewSource(
                source_id="SRC_API",
                source_type="API",
                datasource_alias="api_ds",
                db_type="",
            )
        ],
        objects=[],
        relations=[],
    )
    result = _serialize_payload(payload)
    sources = result.get("sources", [])
    assert len(sources) == 1
    assert "dbType" not in sources[0]

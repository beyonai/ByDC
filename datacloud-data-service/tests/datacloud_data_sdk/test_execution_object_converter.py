from datacloud_data_sdk.plan.models import (
    ObjectViewField,
    ObjectViewFunction,
    ObjectViewFunctionParam,
    ObjectViewObject,
    ObjectViewPayload,
    ObjectViewSource,
    PlanAggregation,
    PlanStep,
    QueryExecutionPlan,
)
from datacloud_data_sdk.plan.execution_object_converter import ExecutionObjectConverter
from datacloud_data_sdk.executor.models import SqlExecTask, ApiExecTask, ScriptExecTask, KbExecTask


PLAN_WITH_SQL = QueryExecutionPlan(
    question="查商机",
    can_answer=True,
    steps=[PlanStep(
        step_id="s1", type="SQL", source_id="SRC_CRM",
        datasource_alias="crm_db",
        sql_template="SELECT bo_id FROM sales_bo",
        output_ref="bo_list",
    )],
    aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
)

PLAN_WITH_API = QueryExecutionPlan(
    question="查员工",
    can_answer=True,
    steps=[PlanStep(
        step_id="s1", type="API", source_id="SRC_EMP",
        function_id="fn_get_emp",
        params={"names": ["邹海天"]},
        output_ref="emp_list",
        csv_table_name="api_emp",
    )],
    aggregation=PlanAggregation(strategy="SQLITE_MEM", sqlite_sql="SELECT * FROM api_emp", columns=[]),
)

PLAN_WITH_SCRIPT = QueryExecutionPlan(
    question="计算评分",
    can_answer=True,
    steps=[PlanStep(
        step_id="s1", type="SCRIPT",
        action_code="calc_score",
        script="def execute(params):\\n    return {'score': 100}",
        params={"bo_id": "123"},
        output_ref="score_result",
    )],
    aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
)

PLAN_WITH_KB = QueryExecutionPlan(
    question="检索知识库",
    can_answer=True,
    steps=[PlanStep(
        step_id="s1",
        type="KB",
        datasource_alias="kb_docs",
        query="如何配置数据源",
        tags={"category": "config", "version": "v2"},
        output_ref="kb_result",
    )],
    aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
)


def test_sql_step_converts_to_sql_exec_task() -> None:
    tasks = ExecutionObjectConverter().convert(PLAN_WITH_SQL)
    assert len(tasks) == 1
    assert isinstance(tasks[0], SqlExecTask)
    assert tasks[0].datasource_alias == "crm_db"


def test_api_step_converts_to_api_exec_task() -> None:
    tasks = ExecutionObjectConverter().convert(PLAN_WITH_API)
    assert len(tasks) == 1
    assert isinstance(tasks[0], ApiExecTask)
    assert tasks[0].function_code == "fn_get_emp"
    assert tasks[0].params == {"names": ["邹海天"]}


def test_api_step_converts_params_with_mapping_path() -> None:
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_EMP", source_type="API")],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="员工",
                source_id="SRC_EMP",
                fields=[ObjectViewField(name="id", type="string")],
                functions=[
                    ObjectViewFunction(
                        function_code="fn_get_emp",
                        params=[
                            ObjectViewFunctionParam(
                                param_code="emp_no",
                                param_name="员工工号",
                                param_type="STRING",
                                direction="IN",
                                mapping_path="$.requestBody.sql_param_emp_no",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="查员工",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="API",
                function_id="fn_get_emp",
                params={"emp_no": "E001"},
                output_ref="emp_list",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    tasks = ExecutionObjectConverter().convert(plan, payload)
    assert len(tasks) == 1
    assert isinstance(tasks[0], ApiExecTask)
    assert tasks[0].params == {"sql_param_emp_no": "E001"}


def test_script_step_converts_to_script_exec_task() -> None:
    tasks = ExecutionObjectConverter().convert(PLAN_WITH_SCRIPT)
    assert len(tasks) == 1
    assert isinstance(tasks[0], ScriptExecTask)
    assert tasks[0].action_code == "calc_score"
    assert "def execute" in tasks[0].script


def test_kb_step_converts_to_kb_exec_task() -> None:
    tasks = ExecutionObjectConverter().convert(PLAN_WITH_KB)
    assert len(tasks) == 1
    assert isinstance(tasks[0], KbExecTask)
    assert tasks[0].datasource_alias == "kb_docs"
    assert tasks[0].query == "如何配置数据源"
    assert tasks[0].tags == {"category": "config", "version": "v2"}
    assert tasks[0].output_ref == "kb_result"

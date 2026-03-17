from datacloud_data.ontology.term_loader import TermLoader
from datacloud_data.plan.term_resolver import TermResolver
from datacloud_data.plan.models import (
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
from datacloud_data.plan.execution_object_converter import ExecutionObjectConverter
from datacloud_data.executor.models import SqlExecTask, ApiExecTask, ScriptExecTask, KbExecTask
from datacloud_data.ontology.loader import OntologyLoader


# Registry for API step tests: sales_emp has action query_emp -> fn_get_emp
REGISTRY_API = {
    "functions": [
        {
            "function_code": "fn_get_emp",
            "function_type": "API",
            "api_schema": {"servers": [{"url": "http://mock:8080"}], "paths": {}},
        }
    ],
    "objects": [
        {
            "object_code": "sales_emp",
            "object_name": "员工",
            "source_type": "API",
            "fields": [],
            "actions": [
                {
                    "action_code": "query_emp",
                    "action_type": "query",
                    "params": [
                        {"param_code": "names", "direction": "IN", "param_type": "ARRAY"},
                        {"param_code": "userId", "direction": "OUT", "param_type": "STRING", "mapping_path": "$.users[].userId"},
                        {"param_code": "userName", "direction": "OUT", "param_type": "STRING", "mapping_path": "$.users[].userName"},
                    ],
                    "function_refs": ["fn_get_emp"],
                }
            ],
        }
    ],
    "relations": [],
}

# Registry for SCRIPT step tests: sales_bo has action calc_score with script
REGISTRY_SCRIPT = {
    "functions": [],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "商机",
            "source_type": "DB",
            "fields": [],
            "actions": [
                {
                    "action_code": "calc_score",
                    "action_type": "query",
                    "script": "def execute(params):\n    return {'score': 100}",
                    "function_refs": [],
                    "params": [{"param_code": "bo_id", "direction": "IN", "param_type": "STRING"}],
                }
            ],
        }
    ],
    "relations": [],
}


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
        object_id="sales_emp",
        function_id="query_emp",
        params={"names": ["邹海天"]},
        output_ref="api_emp",
    )],
    aggregation=PlanAggregation(strategy="SQLITE_MEM", sqlite_sql="SELECT * FROM api_emp", columns=[]),
)

PLAN_WITH_SCRIPT = QueryExecutionPlan(
    question="计算评分",
    can_answer=True,
    steps=[PlanStep(
        step_id="s1", type="API",
        object_id="sales_bo",
        function_id="calc_score",
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


def test_sql_step_resolves_term_bound_literals() -> None:
    """SQL 步骤中绑定术语字段的字面量会被解析为 code。"""
    loader = TermLoader.from_mapping({
        "status.code": [{"code": "TODO", "label": "待办"}, {"code": "DONE", "label": "已完成"}],
    })
    term_resolver = TermResolver(term_loader=loader)
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_CRM", source_type="DB", datasource_alias="crm_db")],
        objects=[
            ObjectViewObject(
                object_id="sales_bo",
                object_name="商机",
                source_id="SRC_CRM",
                table="sales_bo",
                fields=[
                    ObjectViewField(name="status", type="string", term_set="status.code", source_column="status_code"),
                ],
            )
        ],
        relations=[],
    )
    plan = QueryExecutionPlan(
        question="查待办商机",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="SQL",
                datasource_alias="crm_db",
                sql_template="SELECT * FROM sales_bo WHERE status_code = '待办'",
                output_ref="bo_list",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    tasks = ExecutionObjectConverter(term_resolver=term_resolver).convert(plan, payload)
    assert len(tasks) == 1
    assert isinstance(tasks[0], SqlExecTask)
    assert "status_code = 'TODO'" in tasks[0].sql_template
    assert "'待办'" not in tasks[0].sql_template


def test_api_step_converts_to_api_exec_task() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY_API)
    tasks = ExecutionObjectConverter(loader=loader).convert(PLAN_WITH_API)
    assert len(tasks) == 1
    assert isinstance(tasks[0], ApiExecTask)
    assert tasks[0].object_code == "sales_emp"
    assert tasks[0].action_code == "query_emp"
    assert tasks[0].params == {"names": ["邹海天"]}


def test_api_step_converts_params_with_mapping_path() -> None:
    loader = OntologyLoader()
    loader.load_from_content({
        "functions": [{"function_code": "fn_get_emp", "api_schema": {}}],
        "objects": [
            {
                "object_code": "obj1",
                "object_name": "员工",
                "source_type": "API",
                "fields": [],
                "actions": [
                    {
                        "action_code": "get_emp",
                        "action_type": "query",
                        "params": [
                                {
                                    "param_code": "emp_no",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "mapping_path": "$.requestBody.sql_param_emp_no",
                                },
                                {
                                    "param_code": "emp_id",
                                    "direction": "OUT",
                                    "param_type": "STRING",
                                    "mapping_path": "$.response.emp[].emp_id",
                                },
                            ],
                        "function_refs": ["fn_get_emp"],
                    }
                ],
            }
        ],
        "relations": [],
    })
    plan = QueryExecutionPlan(
        question="查员工",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="API",
                object_id="obj1",
                function_id="get_emp",
                params={"emp_no": "E001"},
                output_ref="emp_list",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    tasks = ExecutionObjectConverter(loader=loader).convert(plan)
    assert len(tasks) == 1
    assert isinstance(tasks[0], ApiExecTask)
    assert tasks[0].params == {"sql_param_emp_no": "E001"}


def test_script_step_converts_to_script_exec_task() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY_SCRIPT)
    tasks = ExecutionObjectConverter(loader=loader).convert(PLAN_WITH_SCRIPT)
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


def test_kb_step_resolves_term_bound_tags() -> None:
    """KB 步骤的 tags 中，绑定术语的 field 值会被解析为 code。"""
    loader = TermLoader.from_mapping({
        "status.code": [{"code": "TODO", "label": "待办"}, {"code": "DONE", "label": "已完成"}],
    })
    term_resolver = TermResolver(term_loader=loader)
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_KB", source_type="KNOWLEDGE_BASE", datasource_alias="kb_docs")],
        objects=[
            ObjectViewObject(
                object_id="kb_doc",
                object_name="知识文档",
                source_id="SRC_KB",
                fields=[
                    ObjectViewField(name="status", type="string", term_set="status.code"),
                    ObjectViewField(name="category", type="string", term_set=None),
                ],
                functions=[],
                actions=[],
            )
        ],
        relations=[],
    )
    plan = QueryExecutionPlan(
        question="检索",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="KB",
                datasource_alias="kb_docs",
                query="配置",
                tags={"status": "待办", "category": "config"},
                output_ref="kb_out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    tasks = ExecutionObjectConverter(term_resolver=term_resolver).convert(plan, payload)
    assert len(tasks) == 1
    assert isinstance(tasks[0], KbExecTask)
    assert tasks[0].tags["status"] == "TODO"
    assert tasks[0].tags["category"] == "config"

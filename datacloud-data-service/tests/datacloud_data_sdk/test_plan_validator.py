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
from datacloud_data_sdk.plan.plan_validator import PlanValidator

PAYLOAD = ObjectViewPayload(
    view_id="v1",
    sources=[ObjectViewSource(source_id="SRC_CRM", source_type="DB", datasource_alias="crm_db")],
    objects=[
        ObjectViewObject(
            object_id="OBJ_BO",
            object_name="商机",
            source_id="SRC_CRM",
            table="sales_bo",
            fields=[
                ObjectViewField(name="bo_id", type="string"),
                ObjectViewField(name="bo_name", type="string"),
            ],
            functions=[],
        )
    ],
    relations=[],
)

VALID_PLAN = QueryExecutionPlan(
    question="查商机",
    can_answer=True,
    steps=[
        PlanStep(
            step_id="step_1",
            type="SQL",
            source_id="SRC_CRM",
            datasource_alias="crm_db",
            sql_template="SELECT bo_id, bo_name FROM sales_bo",
            output_ref="bo_list",
        )
    ],
    aggregation=PlanAggregation(
        strategy="DIRECT",
        final_step_id="step_1",
        columns=[{"name": "bo_id", "label": "商机ID", "type": "string"}],
    ),
)


def test_valid_direct_plan() -> None:
    result = PlanValidator().validate(VALID_PLAN, PAYLOAD)
    assert result.valid is True
    assert result.errors == []


def test_invalid_source_id_fails() -> None:
    bad_plan = QueryExecutionPlan(
        question="查商机",
        can_answer=True,
        steps=[PlanStep(step_id="s1", type="SQL", source_id="NONEXISTENT", output_ref="x")],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    result = PlanValidator().validate(bad_plan, PAYLOAD)
    assert result.valid is False
    assert any("NONEXISTENT" in e for e in result.errors)


def test_direct_plan_missing_final_step_id_fails() -> None:
    bad_plan = QueryExecutionPlan(
        question="查商机",
        can_answer=True,
        steps=[PlanStep(step_id="s1", type="SQL", source_id="SRC_CRM", output_ref="x")],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id=None, columns=[]),
    )
    result = PlanValidator().validate(bad_plan, PAYLOAD)
    assert result.valid is False


def test_sql_field_ref_not_in_object_view_fails() -> None:
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1")],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="测试对象",
                source_id="SRC_DB",
                table="t_test",
                fields=[
                    ObjectViewField(name="id", type="string"),
                    ObjectViewField(name="name", type="string"),
                ],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="SQL",
                source_id="SRC_DB",
                datasource_alias="db1",
                sql_template="SELECT id, name, nonexistent_field FROM t_test",
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("nonexistent_field" in e for e in result.errors)


def test_sql_field_ref_valid_passes() -> None:
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1")],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="测试对象",
                source_id="SRC_DB",
                table="t_test",
                fields=[
                    ObjectViewField(name="id", type="string"),
                    ObjectViewField(name="name", type="string"),
                ],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="SQL",
                source_id="SRC_DB",
                datasource_alias="db1",
                sql_template="SELECT id, name FROM t_test WHERE id = '1'",
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert result.valid


def test_api_step_unknown_function_id_fails() -> None:
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_API", source_type="API")],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="测试对象",
                source_id="SRC_API",
                fields=[ObjectViewField(name="id", type="string")],
                functions=[ObjectViewFunction(function_code="fn_real")],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="API",
                source_id="SRC_API",
                function_id="fn_nonexistent",
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("fn_nonexistent" in e for e in result.errors)


def test_api_step_missing_required_param_fails() -> None:
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_API", source_type="API")],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="测试对象",
                source_id="SRC_API",
                fields=[ObjectViewField(name="id", type="string")],
                functions=[
                    ObjectViewFunction(
                        function_code="fn_real",
                        params=[
                            ObjectViewFunctionParam(
                                param_code="userIds",
                                param_name="用户ID列表",
                                param_type="ARRAY",
                                direction="IN",
                                required=True,
                            )
                        ],
                    )
                ],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="API",
                source_id="SRC_API",
                function_id="fn_real",
                params={},
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("userIds" in e and "missing" in e for e in result.errors)


def test_api_step_unknown_param_fails() -> None:
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_API", source_type="API")],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="测试对象",
                source_id="SRC_API",
                fields=[ObjectViewField(name="id", type="string")],
                functions=[
                    ObjectViewFunction(
                        function_code="fn_real",
                        params=[
                            ObjectViewFunctionParam(
                                param_code="userIds",
                                param_name="用户ID列表",
                                param_type="ARRAY",
                                direction="IN",
                                required=True,
                            )
                        ],
                    )
                ],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="API",
                source_id="SRC_API",
                function_id="fn_real",
                params={"userIds": ["x"], "invalid_key": 1},
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("invalid_key" in e for e in result.errors)


def test_api_step_valid_params_passes() -> None:
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_API", source_type="API")],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="测试对象",
                source_id="SRC_API",
                fields=[ObjectViewField(name="id", type="string")],
                functions=[
                    ObjectViewFunction(
                        function_code="fn_real",
                        params=[
                            ObjectViewFunctionParam(
                                param_code="userIds",
                                param_name="用户ID列表",
                                param_type="ARRAY",
                                direction="IN",
                                required=True,
                            )
                        ],
                    )
                ],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="API",
                source_id="SRC_API",
                function_id="fn_real",
                params={"userIds": ["u1"]},
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert result.valid

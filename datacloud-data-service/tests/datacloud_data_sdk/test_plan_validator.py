from datacloud_data_sdk.plan.models import (
    ObjectViewAction,
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
    sources=[
        ObjectViewSource(source_id="SRC_CRM", source_type="DB", datasource_alias="crm_db", db_type="POSTGRESQL")
    ],
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

def test_custom() -> None:
    result = PlanValidator().validate(VALID_PLAN, PAYLOAD)
    assert result.valid is True
    assert result.errors == []


def test_invalid_source_id_fails() -> None:
    bad_plan = QueryExecutionPlan(
        question="查商机",
        can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="SQL", source_id="NONEXISTENT", output_ref="x")
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    result = PlanValidator().validate(bad_plan, PAYLOAD)
    assert result.valid is False
    assert any("NONEXISTENT" in e for e in result.errors)


def test_missing_output_ref_fails() -> None:
    """Step without output_ref (or empty) must fail validation."""
    bad_plan = QueryExecutionPlan(
        question="查商机",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="SQL",
                source_id="SRC_CRM",
                datasource_alias="crm_db",
                sql_template="SELECT 1",
                output_ref="",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    result = PlanValidator().validate(bad_plan, PAYLOAD)
    assert result.valid is False
    assert any("output_ref" in e for e in result.errors)


def test_direct_plan_missing_final_step_id_fails() -> None:
    bad_plan = QueryExecutionPlan(
        question="查商机",
        can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="SQL", source_id="SRC_CRM", output_ref="x")
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id=None, columns=[]),
    )
    result = PlanValidator().validate(bad_plan, PAYLOAD)
    assert result.valid is False


def test_sql_field_ref_not_in_object_view_fails() -> None:
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1", db_type="POSTGRESQL")],
        objects=[
            ObjectViewObject(
                object_id="obj1", object_name="测试对象", source_id="SRC_DB",
                table="t_test",
                fields=[
                    ObjectViewField(name="id", type="string"),
                    ObjectViewField(name="name", type="string"),
                ],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test", can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="SQL", source_id="SRC_DB",
                     datasource_alias="db1",
                     sql_template="SELECT id, name, nonexistent_field FROM t_test",
                     output_ref="out")
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("nonexistent_field" in e for e in result.errors)


def test_sql_field_ref_valid_passes() -> None:
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1", db_type="POSTGRESQL")],
        objects=[
            ObjectViewObject(
                object_id="obj1", object_name="测试对象", source_id="SRC_DB",
                table="t_test",
                fields=[
                    ObjectViewField(name="id", type="string"),
                    ObjectViewField(name="name", type="string"),
                ],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test", can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="SQL", source_id="SRC_DB",
                     datasource_alias="db1",
                     sql_template="SELECT id, name FROM t_test WHERE id = '1'",
                     output_ref="out")
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert result.valid


def test_api_step_missing_object_id_fails() -> None:
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_API", source_type="API")],
        objects=[
            ObjectViewObject(
                object_id="obj1", object_name="测试对象", source_id="SRC_API",
                fields=[], functions=[], actions=[ObjectViewAction(action_code="fn_real", implementation_type="API")],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test", can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="API", source_id="SRC_API",
                     function_id="fn_real", output_ref="out")
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("object_id required" in e for e in result.errors)


def test_api_step_unknown_function_id_fails() -> None:
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_API", source_type="API")],
        objects=[
            ObjectViewObject(
                object_id="obj1", object_name="测试对象", source_id="SRC_API",
                fields=[ObjectViewField(name="id", type="string")],
                functions=[ObjectViewFunction(function_code="fn_real")],
                actions=[ObjectViewAction(action_code="fn_real", implementation_type="API")],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test", can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="API", source_id="SRC_API",
                     object_id="obj1", function_id="fn_nonexistent", output_ref="out")
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
                object_id="obj1", object_name="测试对象", source_id="SRC_API",
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
                actions=[
                    ObjectViewAction(
                        action_code="fn_real",
                        implementation_type="API",
                        input_params=[
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
        question="test", can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="API", source_id="SRC_API",
                     object_id="obj1", function_id="fn_real", params={}, output_ref="out")
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
                object_id="obj1", object_name="测试对象", source_id="SRC_API",
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
                actions=[
                    ObjectViewAction(
                        action_code="fn_real",
                        implementation_type="API",
                        input_params=[
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
        question="test", can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="API", source_id="SRC_API",
                     object_id="obj1", function_id="fn_real",
                     params={"userIds": ["x"], "invalid_key": 1},
                     output_ref="out")
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
                object_id="obj1", object_name="测试对象", source_id="SRC_API",
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
                actions=[
                    ObjectViewAction(
                        action_code="fn_real",
                        implementation_type="API",
                        input_params=[
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
        question="test", can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="API", source_id="SRC_API",
                     object_id="obj1", function_id="fn_real", params={"userIds": ["u1"]},
                     output_ref="out")
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert result.valid


def test_sql_use_name_instead_of_source_column_fails() -> None:
    """SQL 使用 name（如 boName）而非 source_column（如 bo_name）时，校验失败。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[
            ObjectViewSource(
                source_id="SRC_DB",
                source_type="DB",
                datasource_alias="db1",
                db_type="POSTGRESQL",
            )
        ],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="商机对象",
                source_id="SRC_DB",
                table="sales_business_opportunity",
                fields=[
                    ObjectViewField(name="id", type="bigint", source_column="id"),
                    ObjectViewField(name="boName", type="string", source_column="bo_name"),
                    ObjectViewField(
                        name="iwhaleCbmEmpNo",
                        type="string",
                        source_column="iwhale_cbm_emp_no",
                    ),
                ],
            )
        ],
        relations=[],
    )
    # 错误：SQL 中用了 boName（name）而非 bo_name（source_column）
    plan = QueryExecutionPlan(
        question="查杜成鹏跟进的商机",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="SQL",
                source_id="SRC_DB",
                datasource_alias="db1",
                sql_template="SELECT t1.id AS id, t1.boName AS boName, t1.iwhaleCbmEmpNo AS iwhaleCbmEmpNo "
                "FROM sales_business_opportunity t1 WHERE t1.iwhaleCbmEmpNo = '杜成鹏'",
                output_ref="bo_list",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    # 错误信息中会包含 boname（小写），因 SQL 中用了 boName 而非 bo_name
    assert any("boname" in e.lower() for e in result.errors)


def test_sql_field_ref_source_column_passes() -> None:
    """SQL 使用 source_column（物理列名）时，校验通过。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1", db_type="POSTGRESQL")],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="KPI对象",
                source_id="SRC_DB",
                table="kpi_table",
                fields=[
                    ObjectViewField(name="empNo", type="string", source_column="emp_no"),
                    ObjectViewField(
                        name="completedContractAmount",
                        type="number",
                        source_column="completed_contract_amount",
                    ),
                ],
            )
        ],
        relations=[],
    )
    plan = QueryExecutionPlan(
        question="查KPI",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="SQL",
                source_id="SRC_DB",
                datasource_alias="db1",
                sql_template="SELECT emp_no, completed_contract_amount FROM kpi_table",
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert result.valid, result.errors


def test_sql_step_db_source_missing_db_type_fails() -> None:
    """DB 类数据源缺少 db_type 时校验失败。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[
            ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1", db_type="")
        ],
        objects=[
            ObjectViewObject(object_id="o1", object_name="测试", source_id="SRC_DB", table="t1", fields=[])
        ],
        relations=[],
    )
    plan = QueryExecutionPlan(
        question="test", can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="SQL", source_id="SRC_DB", datasource_alias="db1", sql_template="SELECT 1", output_ref="out")
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("missing db_type" in e for e in result.errors)


def test_sql_step_db_source_invalid_db_type_fails() -> None:
    """db_type 不在支持列表时校验失败。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[
            ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1", db_type="ORACLE")
        ],
        objects=[
            ObjectViewObject(object_id="o1", object_name="测试", source_id="SRC_DB", table="t1", fields=[])
        ],
        relations=[],
    )
    plan = QueryExecutionPlan(
        question="test", can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="SQL", source_id="SRC_DB", datasource_alias="db1", sql_template="SELECT 1", output_ref="out")
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("unsupported db_type" in e for e in result.errors)


def test_sql_postgresql_type_cast_passes() -> None:
    """PostgreSQL ::type 类型转换语法（如 contact_scale::DECIMAL）应校验通过。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[
            ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="ds_crm", db_type="POSTGRESQL")
        ],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="KPI汇总",
                source_id="SRC_DB",
                table="sales_person_kpi_summary",
                fields=[
                    ObjectViewField(name="contact_scale", type="string"),
                ],
            )
        ],
        relations=[],
    )
    plan = QueryExecutionPlan(
        question="合同总金额",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="SQL",
                source_id="SRC_DB",
                datasource_alias="ds_crm",
                sql_template="SELECT SUM(contact_scale::DECIMAL) AS totalContractAmount FROM sales_person_kpi_summary WHERE contact_scale IS NOT NULL AND contact_scale != ''",
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert result.valid, result.errors


def test_sql_step_db_source_valid_db_type_passes() -> None:
    """db_type 合法时校验通过。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[
            ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1", db_type="POSTGRESQL")
        ],
        objects=[
            ObjectViewObject(object_id="o1", object_name="测试", source_id="SRC_DB", table="t1", fields=[])
        ],
        relations=[],
    )
    plan = QueryExecutionPlan(
        question="test", can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="SQL", source_id="SRC_DB", datasource_alias="db1", sql_template="SELECT 1", output_ref="out")
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1", columns=[]),
    )
    result = PlanValidator().validate(plan, payload)
    assert result.valid


def test_crm_opportunity_no_change_over_month_sql_passes() -> None:
    """验证商机超过一个月未变更推进的 SQL 中引用不存在字段会被拦截。"""
    payload = ObjectViewPayload(
        view_id="auto_view",
        sources=[
            ObjectViewSource(source_id="SRC_API", source_type="API", datasource_alias=""),
            ObjectViewSource(
                source_id="SRC_DS_CRM",
                source_type="DB",
                datasource_alias="ds_crm",
                db_type="OPENGAUSS"
            ),
            ObjectViewSource(
                source_id="SRC_DS_ATTENDANCE",
                source_type="DB",
                datasource_alias="ds_attendance",
                db_type="OPENGAUSS",
            ),
        ],
        objects=[
            ObjectViewObject(
                object_id="sales_business_opportunity",
                object_name="商机对象",
                source_id="SRC_DS_CRM",
                table="sales_business_opportunity",
                fields=[
                    ObjectViewField(name="id", type="bigint", source_column="id"),
                    ObjectViewField(name="boName", type="string", source_column="bo_name"),
                    ObjectViewField(
                        name="iwhaleCbmEmpNo",
                        type="string",
                        source_column="iwhale_cbm_emp_no",
                    ),
                    ObjectViewField(
                        name="iwhaleCbmName",
                        type="string",
                        source_column="iwhale_cbm_name",
                    ),
                    ObjectViewField(
                        name="customerName",
                        type="string",
                        source_column="customer_name",
                    ),
                    ObjectViewField(
                        name="businessOpportunityProcess",
                        type="string",
                        source_column="business_opportunity_process",
                    ),
                    ObjectViewField(
                        name="opportunityStage",
                        type="string",
                        source_column="opportunity_stage",
                    ),
                ],
            ),
            ObjectViewObject(
                object_id="sales_bo_status_change",
                object_name="商机状态变更对象",
                source_id="SRC_DS_CRM",
                table="sales_bo_status_change",
                fields=[
                    ObjectViewField(name="id", type="bigint", source_column="id"),
                    ObjectViewField(name="boId", type="bigint", source_column="bo_id"),
                    ObjectViewField(
                        name="changedTime",
                        type="timestamp",
                        source_column="changed_time",
                    ),
                ],
            ),
            ObjectViewObject(
                object_id="todo_items",
                object_name="待办事项",
                source_id="SRC_API",
                table="todo_items",
                fields=[
                    ObjectViewField(
                        name="createdAt",
                        type="timestamp",
                        source_column="created_at",
                    ),
                ],
            ),
        ],
        relations=[],
    )

    sql = (
        "SELECT bo.id AS id, bo.bo_name AS boName, bo.iwhale_cbm_emp_no AS iwhaleCbmEmpNo, "
        "bo.iwhale_cbm_name AS iwhaleCbmName, bo.customer_name AS customerName, "
        "bo.business_opportunity_process AS businessOpportunityProcess, "
        "bo.opportunity_stage AS opportunityStage, "
        "MAX(sc.changed_time) AS lastChangeTime "
        "FROM sales_business_opportunity bo "
        "LEFT JOIN sales_bo_status_change sc ON bo.id = sc.bo_id "
        "WHERE bo.id IS NOT NULL "
        "GROUP BY bo.id, bo.bo_name, bo.iwhale_cbm_emp_no, bo.iwhale_cbm_name, "
        "bo.customer_name, bo.business_opportunity_process, bo.opportunity_stage "
        "HAVING (MAX(sc.changed_time) IS NULL AND bo.created_at < '2026-02-13'::DATE) "
        "OR (MAX(sc.changed_time) < '2026-02-13'::DATE - INTERVAL '1 month')"
    )

    plan = QueryExecutionPlan(
        question="帮我查询超过一个月没有变更推进的商机",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1",
                type="SQL",
                source_id="SRC_DS_CRM",
                datasource_alias="ds_crm",
                sql_template=sql,
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(
            strategy="DIRECT",
            final_step_id="s1",
            columns=[
                {"name": "id", "label": "主键ID", "type": "bigint"},
                {"name": "boName", "label": "商机名称", "type": "string"},
                {
                    "name": "iwhaleCbmEmpNo",
                    "label": "商机负责人工号或名称",
                    "type": "string",
                },
                {
                    "name": "iwhaleCbmName",
                    "label": "商机负责人名称",
                    "type": "string",
                },
                {"name": "customerName", "label": "客户名称", "type": "string"},
                {"name": "businessOpportunityProcess", "label": "商机状态", "type": "string"},
                {"name": "opportunityStage", "label": "商机进展", "type": "string"},
                {"name": "lastChangeTime", "label": "最后变更时间", "type": "timestamp"},
            ],
        ),
    )

    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    # bo.created_at 在 sales_business_opportunity 上不存在，应当被识别为 UNKNOWN_COLUMN
    assert any("created_at" in e for e in result.errors)


def test_sql_column_in_function_invalid_fails() -> None:
    """函数参数中的列（如 SUM(t.nonexistent_col)）不存在时校验失败。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[
            ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1", db_type="POSTGRESQL")
        ],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="测试对象",
                source_id="SRC_DB",
                table="t_test",
                fields=[
                    ObjectViewField(name="id", type="string"),
                    ObjectViewField(name="amount", type="decimal"),
                ],
            )
        ],
        relations=[],
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
                sql_template="SELECT t.id, SUM(t.nonexistent_col) FROM t_test t GROUP BY t.id",
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("nonexistent_col" in e for e in result.errors)


def test_sql_ambiguous_column_fails() -> None:
    """多表 JOIN 时裸列 id 出现在多张表，应报 AMBIGUOUS_COLUMN。"""
    payload = ObjectViewPayload(
        view_id="v1",
        sources=[
            ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1", db_type="POSTGRESQL")
        ],
        objects=[
            ObjectViewObject(
                object_id="obj1",
                object_name="表1",
                source_id="SRC_DB",
                table="t1",
                fields=[
                    ObjectViewField(name="id", type="string"),
                    ObjectViewField(name="name", type="string"),
                ],
            ),
            ObjectViewObject(
                object_id="obj2",
                object_name="表2",
                source_id="SRC_DB",
                table="t2",
                fields=[
                    ObjectViewField(name="id", type="string"),
                    ObjectViewField(name="ref_id", type="string"),
                ],
            ),
        ],
        relations=[],
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
                sql_template="SELECT id FROM t1 JOIN t2 ON t1.id = t2.ref_id",
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("AMBIGUOUS_COLUMN" in e or "ambiguous" in e.lower() for e in result.errors)

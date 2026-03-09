"""测试 param_converter。"""
from datacloud_data_sdk.plan.models import ObjectViewFunctionParam
from datacloud_data_sdk.plan.param_converter import map_to_physical


def test_map_to_physical_simple() -> None:
    in_params = [
        ObjectViewFunctionParam(
            param_code="userIds",
            param_name="用户ID列表",
            param_type="ARRAY",
            direction="IN",
            required=True,
            mapping_path="$.requestBody.userIds",
        )
    ]
    result = map_to_physical({"userIds": ["u1", "u2"]}, in_params)
    assert result == {"userIds": ["u1", "u2"]}


def test_map_to_physical_different_physical_key() -> None:
    in_params = [
        ObjectViewFunctionParam(
            param_code="emp_no",
            param_name="员工工号",
            param_type="STRING",
            direction="IN",
            required=True,
            mapping_path="$.requestBody.sql_param_emp_no",
        )
    ]
    result = map_to_physical({"emp_no": "E001"}, in_params)
    assert result == {"sql_param_emp_no": "E001"}


def test_map_to_physical_uses_default_value() -> None:
    in_params = [
        ObjectViewFunctionParam(
            param_code="datasource_id",
            param_name="数据源",
            param_type="STRING",
            direction="IN",
            required=False,
            mapping_path="$.requestBody.datasource_id",
            default_value="ds_sales",
        )
    ]
    result = map_to_physical({}, in_params)
    assert result == {"datasource_id": "ds_sales"}


def test_map_to_physical_skips_out_params() -> None:
    in_params = [
        ObjectViewFunctionParam(
            param_code="userIds",
            param_name="用户ID列表",
            param_type="ARRAY",
            direction="IN",
            mapping_path="$.requestBody.userIds",
        ),
        ObjectViewFunctionParam(
            param_code="userName",
            param_name="用户名称",
            param_type="STRING",
            direction="OUT",
            mapping_path="$.response.users[].userName",
        ),
    ]
    result = map_to_physical({"userIds": ["x"], "userName": "ignored"}, in_params)
    assert result == {"userIds": ["x"]}

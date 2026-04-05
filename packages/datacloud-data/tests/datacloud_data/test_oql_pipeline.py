"""
OQL Pipeline 执行器测试
"""

import pytest
from datacloud_data_sdk.oql.pipeline_executor import RefResolver, PipelineExecutor
from datacloud_data_sdk.models import OQLError, OQLErrorCode


class TestRefResolver:
    """测试 $ref 表达式解析"""

    def test_resolve_list_with_field(self):
        """解析 [*].field 表达式"""
        context = {
            "step1": {
                "records": [
                    {"id": 1, "name": "A"},
                    {"id": 2, "name": "B"},
                    {"id": 1, "name": "A"},  # 重复
                ]
            }
        }

        result = RefResolver.resolve("{step1}.result[*].id", context)
        assert result == [1, 2]  # 去重

    def test_resolve_single_record(self):
        """解析 [N] 表达式"""
        context = {
            "step1": {
                "records": [
                    {"id": 1, "name": "A"},
                    {"id": 2, "name": "B"},
                ]
            }
        }

        result = RefResolver.resolve("{step1}.result[0]", context)
        assert result == {"id": 1, "name": "A"}

    def test_resolve_single_field(self):
        """解析 [N].field 表达式"""
        context = {
            "step1": {
                "records": [
                    {"id": 1, "name": "A"},
                    {"id": 2, "name": "B"},
                ]
            }
        }

        result = RefResolver.resolve("{step1}.result[0].id", context)
        assert result == 1

    def test_resolve_all_records(self):
        """解析 [*] 表达式"""
        context = {
            "step1": {
                "records": [
                    {"id": 1, "name": "A"},
                    {"id": 2, "name": "B"},
                ]
            }
        }

        result = RefResolver.resolve("{step1}.result[*]", context)
        assert len(result) == 2

    def test_resolve_nested_params(self):
        """解析嵌套参数中的 $ref"""
        context = {
            "step1": {
                "records": [
                    {"id": 1},
                    {"id": 2},
                ]
            }
        }

        params = {
            "where": [
                {"field": "id", "op": "in", "value": "{step1}.result[*].id"}
            ]
        }

        result = RefResolver.resolve(params, context)
        assert result["where"][0]["value"] == [1, 2]

    def test_resolve_invalid_ref(self):
        """无效的 $ref 表达式"""
        context = {}

        with pytest.raises(OQLError) as exc_info:
            RefResolver.resolve("{invalid_syntax", context)
        # 不是 $ref 表达式，直接返回
        assert "{invalid_syntax" == RefResolver.resolve("{invalid_syntax", context)

    def test_resolve_missing_step(self):
        """引用不存在的步骤"""
        context = {}

        with pytest.raises(OQLError) as exc_info:
            RefResolver.resolve("{nonexistent}.result[0]", context)
        assert exc_info.value.code == OQLErrorCode.OQL_ERR_INVALID_REF

    def test_resolve_index_out_of_range(self):
        """索引超出范围"""
        context = {
            "step1": {
                "records": [
                    {"id": 1},
                ]
            }
        }

        with pytest.raises(OQLError) as exc_info:
            RefResolver.resolve("{step1}.result[10]", context)
        assert exc_info.value.code == OQLErrorCode.OQL_ERR_INVALID_REF


class TestPipelineExecutor:
    """测试 Pipeline 执行器"""

    def test_max_steps_exceeded(self):
        """步骤数超过限制"""
        executor = PipelineExecutor()
        steps = [{"step_id": f"step{i}", "parameters": {}} for i in range(15)]

        with pytest.raises(OQLError) as exc_info:
            executor.execute(steps, None, None, None, None)
        assert exc_info.value.code == OQLErrorCode.OQL_ERR_STEP_LIMIT_EXCEEDED

"""
ExecuteAction 工具单元测试
"""

import pytest
from unittest.mock import Mock, patch
from datacloud_analysis.tools.oql.execute_action import execute_action
from datacloud_data_sdk.oql import OQLError, OQLErrorCode


@pytest.fixture
def mock_action_service():
    """Mock Action Service"""
    with patch("datacloud_analysis.tools.oql.execute_action.get_action_service") as mock_service:
        service = Mock()
        mock_service.return_value = service
        yield service


class TestExecuteAction:
    """ExecuteAction 工具测试"""

    def test_create_action(self, mock_action_service):
        """测试创建动作"""
        mock_action_service.execute.return_value = {
            "affected_count": 1,
            "affected_objects": ["EMP001"],
            "details": {"created_id": "EMP001"},
        }

        result = execute_action.invoke({
            "action_type": "创建员工",
            "payload": {
                "姓名": "张三",
                "部门": "技术部",
                "职位": "工程师",
            },
        })

        assert result["status"] == "success"
        assert result["tool"] == "ExecuteAction"
        assert result["result"]["action_type"] == "创建员工"
        assert result["result"]["affected_count"] == 1
        assert result["result"]["affected_objects"] == ["EMP001"]

        # 验证调用参数
        mock_action_service.execute.assert_called_once()
        call_args = mock_action_service.execute.call_args[0][0]
        assert call_args["action_type"] == "创建员工"
        assert call_args["payload"]["姓名"] == "张三"

    def test_update_action(self, mock_action_service):
        """测试更新动作"""
        mock_action_service.execute.return_value = {
            "affected_count": 2,
            "affected_objects": ["EMP001", "EMP002"],
            "details": {},
        }

        result = execute_action.invoke({
            "action_type": "更新员工信息",
            "target_objects": ["EMP001", "EMP002"],
            "payload": {"部门": "产品部"},
        })

        assert result["status"] == "success"
        assert result["result"]["affected_count"] == 2
        assert len(result["result"]["affected_objects"]) == 2

    def test_delete_action(self, mock_action_service):
        """测试删除动作"""
        mock_action_service.execute.return_value = {
            "affected_count": 1,
            "affected_objects": ["EMP003"],
            "details": {},
        }

        result = execute_action.invoke({
            "action_type": "删除员工",
            "target_objects": ["EMP003"],
        })

        assert result["status"] == "success"
        assert result["result"]["affected_count"] == 1

    def test_custom_business_action(self, mock_action_service):
        """测试自定义业务动作"""
        mock_action_service.execute.return_value = {
            "affected_count": 2,
            "affected_objects": ["FL001", "FL002"],
            "details": {
                "notification_sent": True,
                "recipients": ["13800138000", "13900139000"],
            },
        }

        result = execute_action.invoke({
            "action_type": "发送延误通知",
            "target_objects": ["FL001", "FL002"],
            "payload": {
                "通知类型": "短信",
                "模板": "延误致歉",
            },
        })

        assert result["status"] == "success"
        assert result["result"]["details"]["notification_sent"] is True

    def test_action_without_target_objects(self, mock_action_service):
        """测试不需要目标对象的动作"""
        mock_action_service.execute.return_value = {
            "affected_count": 0,
            "affected_objects": [],
            "details": {"task_id": "TASK001"},
        }

        result = execute_action.invoke({
            "action_type": "触发批量任务",
            "payload": {"task_type": "数据同步"},
        })

        assert result["status"] == "success"
        call_args = mock_action_service.execute.call_args[0][0]
        assert "target_objects" not in call_args

    def test_action_without_payload(self, mock_action_service):
        """测试不需要 payload 的动作"""
        mock_action_service.execute.return_value = {
            "affected_count": 1,
            "affected_objects": ["EMP001"],
            "details": {},
        }

        result = execute_action.invoke({
            "action_type": "激活员工",
            "target_objects": ["EMP001"],
        })

        assert result["status"] == "success"
        call_args = mock_action_service.execute.call_args[0][0]
        assert "payload" not in call_args

    def test_oql_error_handling(self, mock_action_service):
        """测试 OQL 错误处理"""
        mock_action_service.execute.side_effect = OQLError(
            OQLErrorCode.OQL_ERR_UNKNOWN_OBJECT,
            "动作 'UnknownAction' 不存在",
            {"action_type": "UnknownAction"},
        )

        result = execute_action.invoke({"action_type": "UnknownAction"})

        assert result["status"] == "error"
        assert result["error_code"] == "OQL_ERR_UNKNOWN_OBJECT"
        assert "不存在" in result["message"]

    def test_unexpected_error_handling(self, mock_action_service):
        """测试未预期异常处理"""
        mock_action_service.execute.side_effect = RuntimeError("数据库连接失败")

        result = execute_action.invoke({
            "action_type": "创建员工",
            "payload": {"姓名": "张三"},
        })

        assert result["status"] == "error"
        assert result["error_code"] == "INTERNAL_ERROR"
        assert "数据库连接失败" in result["message"]
        assert result["detail"]["exception_type"] == "RuntimeError"

    def test_empty_result(self, mock_action_service):
        """测试空结果（没有影响任何对象）"""
        mock_action_service.execute.return_value = {
            "affected_count": 0,
            "affected_objects": [],
            "details": {"reason": "条件不匹配"},
        }

        result = execute_action.invoke({
            "action_type": "批量更新",
            "target_objects": [],
            "payload": {"status": "active"},
        })

        assert result["status"] == "success"
        assert result["result"]["affected_count"] == 0
        assert result["result"]["affected_objects"] == []

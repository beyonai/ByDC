"""dataCloud Query Tool 单元测试（mock loader，不依赖真实服务）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def mock_loader() -> MagicMock:
    loader = MagicMock()
    obj = MagicMock()
    obj.query = AsyncMock(return_value={"rows": [{"id": 1, "name": "测试客户"}], "total": 1})
    view = MagicMock()
    view.query = AsyncMock(return_value={"rows": [{"revenue": 100}], "total": 1})
    loader.get_object.return_value = obj
    loader.get_view.return_value = view
    return loader


class TestDatacloudTool:
    @pytest.mark.asyncio
    async def test_query_object(self, mock_loader: MagicMock, tmp_path: Path) -> None:
        """resource_type='object' 时应调用 loader.get_object。"""
        with patch("tools.datacloud_tool._get_loader", return_value=mock_loader):
            from tools.datacloud_tool import build_datacloud_tool

            tool = build_datacloud_tool(tmp_path)
            result = await tool.ainvoke(
                {
                    "resource_code": "by_customer",
                    "resource_type": "object",
                    "question": "查询前5条客户",
                }
            )

        mock_loader.get_object.assert_called_once_with("by_customer")
        assert "测试客户" in result

    @pytest.mark.asyncio
    async def test_query_view(self, mock_loader: MagicMock, tmp_path: Path) -> None:
        """resource_type='view' 时应调用 loader.get_view。"""
        with patch("tools.datacloud_tool._get_loader", return_value=mock_loader):
            from tools.datacloud_tool import build_datacloud_tool

            tool = build_datacloud_tool(tmp_path)
            result = await tool.ainvoke(
                {
                    "resource_code": "scene_sales",
                    "resource_type": "view",
                    "question": "统计各行业销售额",
                }
            )

        mock_loader.get_view.assert_called_once_with("scene_sales")
        assert "revenue" in result

    @pytest.mark.asyncio
    async def test_query_error_returns_message(
        self, mock_loader: MagicMock, tmp_path: Path
    ) -> None:
        """底层抛异常时应返回友好错误信息，不向上传播。"""
        mock_loader.get_object.side_effect = RuntimeError("连接失败")
        with patch("tools.datacloud_tool._get_loader", return_value=mock_loader):
            from tools.datacloud_tool import build_datacloud_tool

            tool = build_datacloud_tool(tmp_path)
            result = await tool.ainvoke(
                {
                    "resource_code": "by_customer",
                    "resource_type": "object",
                    "question": "查询客户",
                }
            )

        assert "查询失败" in result
        assert "连接失败" in result

"""本体加载器 - 支持三种模式。

模式1：MCP模式 - 通过MCP客户端连接到datacloud-data服务
模式2：动态Tool加载模式 - 从OWL文件生成专用工具
模式3：统一接口模式 - 使用query_objects和execute_action（当前默认）
"""

from __future__ import annotations

import logging
from typing import Any
from pathlib import Path

logger = logging.getLogger(__name__)


class OntologyLoader:
    """本体加载器基类。"""

    def load_tools(self, mounted_objects: list[str] | None = None) -> list[Any]:
        """加载本体工具。

        Args:
            mounted_objects: 挂载的对象/视图列表

        Returns:
            工具列表
        """
        raise NotImplementedError


class UnifiedInterfaceLoader(OntologyLoader):
    """模式3：统一接口模式（当前实现）。

    使用query_objects和execute_action两个通用工具。
    """

    def load_tools(self, mounted_objects: list[str] | None = None) -> list[Any]:
        """加载统一接口工具。"""
        from datacloud_analysis.tools.oql import register_all_tools

        logger.info("UnifiedInterfaceLoader: loading unified interface tools")
        tools = register_all_tools()
        logger.info("UnifiedInterfaceLoader: loaded %d tools", len(tools))
        return tools


class MCPLoader(OntologyLoader):
    """模式1：MCP模式。

    通过MCP客户端连接到datacloud-data服务，动态获取工具列表。
    """

    def __init__(self, mcp_endpoint: str):
        """初始化MCP加载器。

        Args:
            mcp_endpoint: MCP服务端点，如 http://localhost:8080/api/v1/mcp/
        """
        self.mcp_endpoint = mcp_endpoint

    def load_tools(self, mounted_objects: list[str] | None = None) -> list[Any]:
        """通过MCP客户端加载工具。"""
        logger.info("MCPLoader: loading tools from MCP endpoint: %s", self.mcp_endpoint)

        try:
            # 导入MCP客户端
            from datacloud_analysis.tools.mcp_client import create_mcp_tools

            # 创建MCP工具
            tools = create_mcp_tools(
                mcp_endpoint=self.mcp_endpoint,
                mounted_objects=mounted_objects or [],
            )

            logger.info("MCPLoader: loaded %d tools from MCP", len(tools))
            return tools

        except ImportError as e:
            logger.error("MCPLoader: failed to import MCP client: %s", e)
            logger.warning("MCPLoader: falling back to unified interface mode")
            return UnifiedInterfaceLoader().load_tools(mounted_objects)
        except Exception as e:
            logger.error("MCPLoader: failed to load MCP tools: %s", e)
            logger.warning("MCPLoader: falling back to unified interface mode")
            return UnifiedInterfaceLoader().load_tools(mounted_objects)


class DynamicToolLoader(OntologyLoader):
    """模式2：动态Tool加载模式。

    从OWL文件解析本体定义，为每个对象生成专用的查询和动作工具。
    """

    def __init__(self, scene_path: str, auto_register: bool = True):
        """初始化动态工具加载器。

        Args:
            scene_path: OWL场景目录路径
            auto_register: 是否自动注册工具
        """
        self.scene_path = Path(scene_path)
        self.auto_register = auto_register

    def load_tools(self, mounted_objects: list[str] | None = None) -> list[Any]:
        """从OWL文件生成动态工具。"""
        logger.info("DynamicToolLoader: loading tools from OWL path: %s", self.scene_path)

        if not self.scene_path.exists():
            logger.error("DynamicToolLoader: scene path does not exist: %s", self.scene_path)
            logger.warning("DynamicToolLoader: falling back to unified interface mode")
            return UnifiedInterfaceLoader().load_tools(mounted_objects)

        try:
            # 导入OWL解析器
            from datacloud_analysis.tools.owl_parser import generate_tools_from_owl

            # 从OWL生成工具
            tools = generate_tools_from_owl(
                scene_path=self.scene_path,
                mounted_objects=mounted_objects or [],
                auto_register=self.auto_register,
            )

            logger.info("DynamicToolLoader: generated %d tools from OWL", len(tools))
            return tools

        except ImportError as e:
            logger.error("DynamicToolLoader: failed to import OWL parser: %s", e)
            logger.warning("DynamicToolLoader: falling back to unified interface mode")
            return UnifiedInterfaceLoader().load_tools(mounted_objects)
        except Exception as e:
            logger.error("DynamicToolLoader: failed to generate tools from OWL: %s", e)
            logger.warning("DynamicToolLoader: falling back to unified interface mode")
            return UnifiedInterfaceLoader().load_tools(mounted_objects)


def create_ontology_loader(
    load_mode: str = "unified_interface",
    mcp_endpoint: str = "",
    scene_path: str = "",
    auto_register: bool = True,
) -> OntologyLoader:
    """创建本体加载器。

    Args:
        load_mode: 加载模式 (mcp | dynamic_tool | unified_interface)
        mcp_endpoint: MCP服务端点（mcp模式）
        scene_path: OWL场景目录（dynamic_tool模式）
        auto_register: 自动注册工具（dynamic_tool模式）

    Returns:
        本体加载器实例
    """
    logger.info("create_ontology_loader: mode=%s", load_mode)

    if load_mode == "mcp":
        if not mcp_endpoint:
            logger.warning("create_ontology_loader: mcp mode requires mcp_endpoint, falling back to unified_interface")
            return UnifiedInterfaceLoader()
        return MCPLoader(mcp_endpoint=mcp_endpoint)

    elif load_mode == "dynamic_tool":
        if not scene_path:
            logger.warning("create_ontology_loader: dynamic_tool mode requires scene_path, falling back to unified_interface")
            return UnifiedInterfaceLoader()
        return DynamicToolLoader(scene_path=scene_path, auto_register=auto_register)

    else:
        # 默认使用统一接口模式
        return UnifiedInterfaceLoader()

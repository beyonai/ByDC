"""测试本体加载的三种模式。

测试场景：
1. 模式3（统一接口）- 默认模式
2. 模式2（动态Tool加载）- 从OWL生成工具
3. 模式1（MCP模式）- 连接MCP服务
"""

import os
import pytest
from pathlib import Path


class TestOntologyLoader:
    """测试本体加载器。"""

    def test_unified_interface_mode(self):
        """测试模式3：统一接口模式。"""
        from datacloud_analysis.tools.ontology_loader import UnifiedInterfaceLoader

        loader = UnifiedInterfaceLoader()
        tools = loader.load_tools(mounted_objects=["Order", "Customer"])

        # 应该返回2个工具：query_objects 和 execute_action
        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "query_objects" in tool_names
        assert "execute_action" in tool_names

    def test_dynamic_tool_mode_no_owl(self):
        """测试模式2：动态Tool加载模式（无OWL文件，应回退）。"""
        from datacloud_analysis.tools.ontology_loader import DynamicToolLoader

        # 使用不存在的路径
        loader = DynamicToolLoader(scene_path="/nonexistent/path", auto_register=True)
        tools = loader.load_tools(mounted_objects=["Order"])

        # 应该回退到统一接口模式
        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "query_objects" in tool_names

    def test_mcp_mode_no_endpoint(self):
        """测试模式1：MCP模式（无端点，应回退）。"""
        from datacloud_analysis.tools.ontology_loader import MCPLoader

        # 使用无效端点
        loader = MCPLoader(mcp_endpoint="http://invalid:9999/mcp/")
        tools = loader.load_tools(mounted_objects=["Order"])

        # 应该回退到统一接口模式
        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "query_objects" in tool_names

    def test_create_ontology_loader_default(self):
        """测试创建本体加载器（默认模式）。"""
        from datacloud_analysis.tools.ontology_loader import create_ontology_loader

        loader = create_ontology_loader()
        tools = loader.load_tools()

        assert len(tools) == 2

    def test_create_ontology_loader_mcp_mode(self):
        """测试创建本体加载器（MCP模式）。"""
        from datacloud_analysis.tools.ontology_loader import create_ontology_loader

        loader = create_ontology_loader(
            load_mode="mcp",
            mcp_endpoint="http://localhost:8080/api/v1/mcp/",
        )

        # 应该返回MCPLoader实例
        from datacloud_analysis.tools.ontology_loader import MCPLoader
        assert isinstance(loader, MCPLoader)

    def test_create_ontology_loader_dynamic_mode(self):
        """测试创建本体加载器（动态Tool模式）。"""
        from datacloud_analysis.tools.ontology_loader import create_ontology_loader

        loader = create_ontology_loader(
            load_mode="dynamic_tool",
            scene_path="/tmp/owl",
        )

        # 应该返回DynamicToolLoader实例
        from datacloud_analysis.tools.ontology_loader import DynamicToolLoader
        assert isinstance(loader, DynamicToolLoader)


class TestOWLParser:
    """测试OWL解析器。"""

    def test_parse_owl_files_empty_dir(self, tmp_path):
        """测试解析空目录。"""
        from datacloud_analysis.tools.owl_parser import parse_owl_files

        ontology = parse_owl_files(tmp_path)
        assert ontology == {"objects": {}}

    def test_parse_owl_files_with_mock_owl(self, tmp_path):
        """测试解析模拟OWL文件。"""
        from datacloud_analysis.tools.owl_parser import parse_owl_files

        # 创建模拟OWL文件
        owl_file = tmp_path / "Order.owl"
        owl_content = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:owl="http://www.w3.org/2002/07/owl#">
    <owl:DatatypeProperty rdf:about="http://example.com#orderId"/>
    <owl:DatatypeProperty rdf:about="http://example.com#customerName"/>
    <owl:ObjectProperty rdf:about="http://example.com#hasCustomer"/>
</rdf:RDF>
"""
        owl_file.write_text(owl_content, encoding="utf-8")

        ontology = parse_owl_files(tmp_path)
        assert "Order" in ontology["objects"]
        assert len(ontology["objects"]["Order"]["properties"]) > 0

    def test_generate_tools_from_owl_empty(self, tmp_path):
        """测试从空OWL目录生成工具。"""
        from datacloud_analysis.tools.owl_parser import generate_tools_from_owl

        tools = generate_tools_from_owl(tmp_path, mounted_objects=["Order"])
        assert len(tools) == 0


class TestMCPClient:
    """测试MCP客户端。"""

    def test_mcp_client_init(self):
        """测试MCP客户端初始化。"""
        from datacloud_analysis.tools.mcp_client import MCPClient

        client = MCPClient(
            endpoint="http://localhost:8080/api/v1/mcp/",
            mounted_objects=["Order", "Customer"],
        )

        assert client.endpoint == "http://localhost:8080/api/v1/mcp"
        assert client.mounted_objects == ["Order", "Customer"]

    def test_create_mcp_tools_no_server(self):
        """测试创建MCP工具（无服务器）。"""
        from datacloud_analysis.tools.mcp_client import create_mcp_tools

        # 使用无效端点，应该返回空列表
        tools = create_mcp_tools(
            mcp_endpoint="http://invalid:9999/mcp/",
            mounted_objects=["Order"],
        )

        assert len(tools) == 0


class TestAgentIntegration:
    """测试Agent集成。"""

    def test_create_agent_with_unified_mode(self, monkeypatch):
        """测试使用统一接口模式创建Agent。"""
        # 设置环境变量
        monkeypatch.setenv("ONTOLOGY_LOAD_MODE", "unified_interface")
        monkeypatch.setenv("DATACLOUD_PG_CHECKPOINT_URI", "postgresql://test:test@localhost/test")
        monkeypatch.setenv("DATACLOUD_WORKSPACE_PUBLIC_ROOT", "/tmp/public")
        monkeypatch.setenv("DATACLOUD_WORKSPACE_PRIVATE_ROOT", "/tmp/private")
        monkeypatch.setenv("DATACLOUD_DATA_SERVICE_BASE_URL", "http://localhost:8080")

        # 注意：这个测试需要完整的环境，这里只验证配置加载
        from datacloud_analysis.config.env import Settings

        settings = Settings()
        assert settings.ontology.load_mode == "unified_interface"

    def test_create_agent_with_mcp_mode(self, monkeypatch):
        """测试使用MCP模式创建Agent。"""
        monkeypatch.setenv("ONTOLOGY_LOAD_MODE", "mcp")
        monkeypatch.setenv("ONTOLOGY_MCP_ENDPOINT", "http://localhost:8080/api/v1/mcp/")
        monkeypatch.setenv("DATACLOUD_PG_CHECKPOINT_URI", "postgresql://test:test@localhost/test")
        monkeypatch.setenv("DATACLOUD_WORKSPACE_PUBLIC_ROOT", "/tmp/public")
        monkeypatch.setenv("DATACLOUD_WORKSPACE_PRIVATE_ROOT", "/tmp/private")
        monkeypatch.setenv("DATACLOUD_DATA_SERVICE_BASE_URL", "http://localhost:8080")

        from datacloud_analysis.config.env import Settings

        settings = Settings()
        assert settings.ontology.load_mode == "mcp"
        assert settings.ontology.mcp_endpoint == "http://localhost:8080/api/v1/mcp/"

    def test_create_agent_with_dynamic_tool_mode(self, monkeypatch):
        """测试使用动态Tool模式创建Agent。"""
        monkeypatch.setenv("ONTOLOGY_LOAD_MODE", "dynamic_tool")
        monkeypatch.setenv("ONTOLOGY_SCENE_PATH", "/app/ontology/owl")
        monkeypatch.setenv("ONTOLOGY_AUTO_REGISTER", "true")
        monkeypatch.setenv("DATACLOUD_PG_CHECKPOINT_URI", "postgresql://test:test@localhost/test")
        monkeypatch.setenv("DATACLOUD_WORKSPACE_PUBLIC_ROOT", "/tmp/public")
        monkeypatch.setenv("DATACLOUD_WORKSPACE_PRIVATE_ROOT", "/tmp/private")
        monkeypatch.setenv("DATACLOUD_DATA_SERVICE_BASE_URL", "http://localhost:8080")

        from datacloud_analysis.config.env import Settings

        settings = Settings()
        assert settings.ontology.load_mode == "dynamic_tool"
        assert settings.ontology.scene_path == "/app/ontology/owl"
        assert settings.ontology.auto_register is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

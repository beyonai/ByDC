"""手动测试本体加载器的三种模式。

运行方式：
python tests/manual_test_ontology.py
"""

import sys
import os
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 80)
print("Test Ontology Loader - Three Modes")
print("=" * 80)

# 测试1：统一接口模式
print("\n[Test 1] Unified Interface Mode")
print("-" * 80)
try:
    from datacloud_analysis.tools.ontology_loader import UnifiedInterfaceLoader

    loader = UnifiedInterfaceLoader()
    tools = loader.load_tools(mounted_objects=["Order", "Customer"])

    print("SUCCESS: Loaded {} tools".format(len(tools)))
    for tool in tools:
        desc = tool.description[:50] if hasattr(tool, "description") else "N/A"
        print("  - {}: {}...".format(tool.name, desc))
except Exception as e:
    print("FAILED: {}".format(e))
    import traceback

    traceback.print_exc()

# 测试2：动态Tool加载模式（无OWL文件，应回退）
print("\n[Test 2] Dynamic Tool Mode (no OWL, should fallback)")
print("-" * 80)
try:
    from datacloud_analysis.tools.ontology_loader import DynamicToolLoader

    loader = DynamicToolLoader(scene_path="/nonexistent/path", auto_register=True)
    tools = loader.load_tools(mounted_objects=["Order"])

    print("SUCCESS: Fallback worked, loaded {} tools".format(len(tools)))
    for tool in tools:
        print("  - {}".format(tool.name))
except Exception as e:
    print("FAILED: {}".format(e))
    import traceback

    traceback.print_exc()

# 测试3：MCP模式（无端点，应回退）
print("\n[Test 3] MCP Mode (no endpoint, should fallback)")
print("-" * 80)
try:
    from datacloud_analysis.tools.ontology_loader import MCPLoader

    loader = MCPLoader(mcp_endpoint="http://invalid:9999/mcp/")
    tools = loader.load_tools(mounted_objects=["Order"])

    print("SUCCESS: Fallback worked, loaded {} tools".format(len(tools)))
    for tool in tools:
        print("  - {}".format(tool.name))
except Exception as e:
    print("FAILED: {}".format(e))
    import traceback

    traceback.print_exc()

# 测试4：创建本体加载器工厂
print("\n[Test 4] Ontology Loader Factory")
print("-" * 80)
try:
    from datacloud_analysis.tools.ontology_loader import create_ontology_loader

    # 默认模式
    loader1 = create_ontology_loader()
    print("SUCCESS: Default mode - {}".format(type(loader1).__name__))

    # MCP模式
    loader2 = create_ontology_loader(
        load_mode="mcp",
        mcp_endpoint="http://localhost:8080/api/v1/mcp/",
    )
    print("SUCCESS: MCP mode - {}".format(type(loader2).__name__))

    # 动态Tool模式
    loader3 = create_ontology_loader(
        load_mode="dynamic_tool",
        scene_path="/tmp/owl",
    )
    print("SUCCESS: Dynamic Tool mode - {}".format(type(loader3).__name__))

except Exception as e:
    print("FAILED: {}".format(e))
    import traceback

    traceback.print_exc()

# 测试5：OWL解析器
print("\n[Test 5] OWL Parser")
print("-" * 80)
try:
    from datacloud_analysis.tools.owl_parser import parse_owl_files
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # 创建模拟OWL文件
        owl_file = tmppath / "Order.owl"
        owl_content = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:owl="http://www.w3.org/2002/07/owl#">
    <owl:DatatypeProperty rdf:about="http://example.com#orderId"/>
    <owl:DatatypeProperty rdf:about="http://example.com#customerName"/>
    <owl:ObjectProperty rdf:about="http://example.com#hasCustomer"/>
</rdf:RDF>
"""
        owl_file.write_text(owl_content, encoding="utf-8")

        ontology = parse_owl_files(tmppath)
        print("SUCCESS: Parsed {} objects".format(len(ontology["objects"])))
        for obj_name, obj_def in ontology["objects"].items():
            print(
                "  - {}: {} properties, {} actions".format(
                    obj_name, len(obj_def["properties"]), len(obj_def["actions"])
                )
            )

except Exception as e:
    print("FAILED: {}".format(e))
    import traceback

    traceback.print_exc()

# 测试6：MCP客户端
print("\n[Test 6] MCP Client")
print("-" * 80)
try:
    from datacloud_analysis.tools.mcp_client import MCPClient

    client = MCPClient(
        endpoint="http://localhost:8080/api/v1/mcp/",
        mounted_objects=["Order", "Customer"],
    )

    print("SUCCESS: Client created")
    print("  - endpoint: {}".format(client.endpoint))
    print("  - mounted_objects: {}".format(client.mounted_objects))

except Exception as e:
    print("FAILED: {}".format(e))
    import traceback

    traceback.print_exc()

# 测试7：环境变量配置
print("\n[Test 7] Environment Configuration")
print("-" * 80)
try:
    # 设置测试环境变量
    os.environ["ONTOLOGY_LOAD_MODE"] = "unified_interface"
    os.environ["ONTOLOGY_MCP_ENDPOINT"] = "http://localhost:8080/api/v1/mcp/"
    os.environ["ONTOLOGY_SCENE_PATH"] = "/app/ontology/owl"
    os.environ["ONTOLOGY_AUTO_REGISTER"] = "true"

    from datacloud_analysis.config.env import OntologySettings

    settings = OntologySettings()
    print("SUCCESS: Configuration loaded")
    print("  - load_mode: {}".format(settings.load_mode))
    print("  - mcp_endpoint: {}".format(settings.mcp_endpoint))
    print("  - scene_path: {}".format(settings.scene_path))
    print("  - auto_register: {}".format(settings.auto_register))

except Exception as e:
    print("FAILED: {}".format(e))
    import traceback

    traceback.print_exc()

print("\n" + "=" * 80)
print("Test Complete")
print("=" * 80)

# Agent调用本体设计方案

## 1. 概述

本方案设计了Worker启动时通过环境变量配置加载本体方法的三种模式，以满足不同场景下Agent与本体交互的需求。

**核心架构说明**：
- **datacloud-analysis**：本体分析引擎，使用Deep Agents SDK创建agent，通过`query_objects`和`execute_action`两个核心工具调用本体
- **datacloud-data**：本体数据引擎，提供MCP服务端点，负责本体数据的查询和操作执行
- **本体加载**：通过环境变量配置不同模式，控制agent如何发现和调用本体能力

## 2. 现有架构分析

### 2.1 当前实现（基于代码分析）

#### 2.1.1 Agent侧（datacloud-analysis）
```python
# src/datacloud_analysis/agent.py
def create_agent(
    mounted_objects: list[str] | None = None,  # 挂载的对象/视图列表
    tools: dict[str, Any] | None = None,       # 其他工具（非OBJECT/VIEW类型）
    ...
):
    # 1. 注册核心OQL工具
    all_tools = register_all_tools()  # 返回 [query_objects, execute_action]
    
    # 2. 添加其他工具（AGENT、FUNCTION等类型）
    if tools:
        all_tools.extend(tools.values())
    
    # 3. 通过中间件注入本体知识
    middlewares = [
        KnowledgeInjectionMiddleware(mounted_objects=mounted_objects),
        ...
    ]
    
    # 4. 创建Deep Agent
    compiled = create_deep_agent(
        tools=all_tools,
        middleware=middlewares,
        ...
    )
```

**核心工具**：
- `query_objects(object_type, filters, fields, limit, ...)`: 查询本体对象数据
- `execute_action(action_type, target_objects, payload)`: 执行本体动作

#### 2.1.2 数据侧（datacloud-data）
```python
# ../datacloud-data/src/datacloud_data_service/api/mcp_sdk_handler.py
# MCP服务端点：http://localhost:8080/api/v1/mcp/

@server.list_tools()
async def list_tools() -> list[Tool]:
    """根据请求头动态返回工具列表"""
    ctx = get_current_context()
    tools = registry.list_tools(
        view_id=ctx.view_id,           # 从 x-view-id header
        object_ids=ctx.object_ids,     # 从 x-object-id header
        tool_list_mode=ctx.tool_list_mode,  # unified | per_object
    )
    return tools

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """执行工具调用"""
    ...
```

**关键请求头**：
- `x-object-id`: 指定要查询的本体对象（单个）
- `x-object-ids`: 指定要查询的本体对象（多个，逗号分隔）
- `x-view-id`: 指定要查询的视图
- `x-tool-list-mode`: 工具列表模式（`unified` | `per_object`）

### 2.2 设计目标

基于当前架构，本方案旨在提供三种本体加载模式，以满足不同场景需求：

1. **模式灵活性**：通过环境变量配置，支持三种不同的工具注册方式
2. **工具发现自动化**：`mounted_objects`由`init_agent_conf.py`自动提取，无需手动配置
3. **向后兼容**：保持当前模式3（统一接口）作为默认模式，确保现有系统稳定运行


## 3. 三种加载模式设计

### 3.1 模式1：MCP模式（远程服务模式）

#### 3.1.1 设计说明
所有本体通过**统一的MCP服务端点**提供能力，通过请求头`x-object-id`区分不同本体。Worker启动时不注册固定的Query/Action工具，而是为每个`mounted_object`动态生成MCP工具。

#### 3.1.2 配置方式
```bash
# 环境变量配置
ONTOLOGY_LOAD_MODE=mcp
ONTOLOGY_MCP_ENDPOINT=http://localhost:8080/api/v1/mcp/  # 统一MCP端点
```

**说明**：
- `mounted_objects`不需要配置环境变量，由`init_agent_conf.py`自动从AI Factory获取
- 插件扫描`relResourceList`，提取`resourceBizType`为`OBJECT`/`VIEW`的资源编码

#### 3.1.3 实现方案

**MCP工具生成器实现**：

**文件**：`src/datacloud_analysis/ontology/mcp_tool_generator.py`

```python
"""MCP工具生成器 - 模式1"""
import httpx
from typing import Any
from langchain_core.tools import tool


def generate_mcp_tools(endpoint: str, mounted_objects: list[str]) -> list[Any]:
    """为每个mounted_object生成MCP调用工具
    
    Args:
        endpoint: MCP服务端点
        mounted_objects: 挂载的对象列表
    
    Returns:
        MCP工具列表
    """
    tools = []
    
    for object_code in mounted_objects:
        # 使用工厂函数避免闭包陷阱
        mcp_tool = _create_mcp_tool(endpoint, object_code)
        tools.append(mcp_tool)
    
    return tools


def _create_mcp_tool(endpoint: str, object_code: str):
    """创建单个MCP工具"""
    
    @tool
    async def mcp_query_tool(
        question: str = None,
        filters: dict = None,
        fields: list[str] = None,
        limit: int = 100,
        **kwargs
    ) -> dict:
        f"""查询{object_code}对象数据（通过MCP协议）
        
        Args:
            question: 自然语言查询问题（可选）
            filters: 结构化过滤条件（可选）
            fields: 返回字段列表（可选）
            limit: 返回数量限制
        
        Returns:
            查询结果
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint,
                headers={
                    "content-type": "application/json",
                    "x-object-id": object_code,
                    "x-tool-list-mode": "per_object",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": f"query_{object_code}",
                        "arguments": {
                            "question": question,
                            "filters": filters,
                            "fields": fields,
                            "limit": limit,
                            **kwargs
                        }
                    }
                },
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
            
            # 提取MCP响应中的结果
            if "result" in result:
                return result["result"]
            elif "error" in result:
                raise RuntimeError(f"MCP调用失败: {result['error']}")
            else:
                return result
    
    # 设置工具名称和描述
    mcp_query_tool.__name__ = f"{object_code}_query"
    mcp_query_tool.name = f"{object_code}_query"
    mcp_query_tool.description = f"查询{object_code}对象数据"
    
    return mcp_query_tool
```

#### 3.1.4 MCP调用报文
```bash
# 1. 获取ads_grid_analysis本体的工具列表
'x-object-id: ads_grid_analysis'  这个是对象或视图的编码。

curl -X POST 'http://localhost:8080/api/v1/mcp/' \
  -H 'content-type: application/json' \
  -H 'x-object-id: ads_grid_analysis' \
  -H 'x-tool-list-mode: per_object' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 响应示例
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "query_ads_grid_analysis",
        "description": "查询广告网格分析数据",
        "inputSchema": {
          "type": "object",
          "properties": {
            "filters": {"type": "object"},
            "fields": {"type": "array"},
            "limit": {"type": "integer"}
          }
        }
      },
      {
        "name": "analyze_grid_performance",
        "description": "分析网格性能",
        "inputSchema": {...}
      }
    ]
  }
}

# 2. 调用工具
'x-object-id: ads_grid_analysis'  这个是对象或视图的编码。
curl -X POST 'http://localhost:8080/api/v1/mcp/' \
  -H 'content-type: application/json' \
  -H 'x-object-id: ads_grid_analysis' \
  -d '{
    "jsonrpc":"2.0",
    "id":2,
    "method":"tools/call",
    "params":{
      "name":"query_ads_grid_analysis",
      "arguments":{
        "filters":{"region":"华东"},
        "fields":["grid_id","coverage"],
        "limit":50
      }
    }
  }'
```

#### 3.1.5 调用流程

```
Agent调用
  ↓
LLM选择工具：ads_grid_analysis_query(question="...")
  ↓
动态生成的MCP工具被调用
  ↓
发起HTTP POST请求到MCP endpoint
  headers: {"x-object-id": "ads_grid_analysis"}
  body: {"method": "tools/call", "params": {...}}
  ↓
datacloud-data MCP服务端处理
  ↓
根据x-object-id加载本体
  ↓
执行query/action
  ↓
返回结果给Agent
```

#### 3.1.6 特点
- ✅ 工具名称明确，每个对象有专属工具（如`ads_grid_analysis_query`）
- ✅ 不支持固定的Query、Action方法（模式1特点）
- ✅ 统一MCP端点，配置简单
- ✅ 服务独立部署，支持分布式
- ✅ datacloud-data已有MCP实现
- ✅ 通过MCP协议标准化工具接口
- ❌ 需要为每个对象生成工具，工具数量多
- ❌ 多一层MCP协议封装，相比直接HTTP调用略有开销

#### 3.1.7 适用场景
- 本体服务独立部署
- 多个Worker共享同一个本体服务
- 需要标准化的MCP协议接口
- 希望工具名称明确（{对象名}_query）
- 需要与其他MCP生态工具集成

#### 3.1.8 验收测试用例

##### 测试用例1：验证MCP工具生成
**前置条件**：
- 环境变量：`ONTOLOGY_LOAD_MODE=mcp`
- 环境变量：`ONTOLOGY_MCP_ENDPOINT=http://localhost:8080/api/v1/mcp/`
- `mounted_objects = ["ads_grid_analysis", "customer_analysis"]`

**测试步骤**：
1. 创建agent
2. 检查注册的工具列表

**预期结果**：
```python
tools = [
    ads_grid_analysis_query,  # ✅ 已生成
    customer_analysis_query,  # ✅ 已生成
]
# ❌ 不包含 query_objects
# ❌ 不包含 execute_action
```

**验证点**：
- ✅ 为每个对象生成专属工具
- ✅ 工具名称格式：`{object_code}_query`
- ✅ 不注册通用工具

---

##### 测试用例2：验证MCP工具调用
**前置条件**：
- Agent已创建（模式1）
- datacloud-data MCP服务运行中

**测试步骤**：
1. LLM调用工具：
```python
ads_grid_analysis_query(
    filters={"region": "华东"},
    limit=10
)
```
2. 检查HTTP请求

**预期结果**：
```bash
POST http://localhost:8080/api/v1/mcp/
Headers:
  x-object-id: ads_grid_analysis
  x-tool-list-mode: per_object
Body:
  {
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "query_ads_grid_analysis",
      "arguments": {"filters": {...}, "limit": 10}
    }
  }
```

**验证点**：
- ✅ 使用MCP协议格式
- ✅ header包含`x-object-id`
- ✅ 返回查询结果

---

##### 测试用例3：验证MCP工具闭包正确性
**前置条件**：
- `mounted_objects = ["obj1", "obj2", "obj3"]`

**测试步骤**：
1. 创建agent（模式1）
2. 分别调用3个工具
3. 检查每个工具的`x-object-id` header

**预期结果**：
```python
obj1_query() → x-object-id: obj1  # ✅ 正确
obj2_query() → x-object-id: obj2  # ✅ 正确
obj3_query() → x-object-id: obj3  # ✅ 正确
# ❌ 不应该都是 obj3（闭包陷阱）
```

**验证点**：
- ✅ 每个工具引用正确的object_code
- ✅ 没有闭包变量捕获问题

---

: {"filters": {...}, "limit": 10}
    }
  }
```

**验证点**：
- ✅ 使用MCP协议格式
- ✅ header包含`x-object-id`
- ✅ 返回查询结果

---

##### 测试用例3：验证MCP工具闭包正确性
**前置条件**：
- `mounted_objects = ["obj1", "obj2", "obj3"]`

**测试步骤**：
1. 创建agent（模式1）
2. 分别调用3个工具
3. 检查每个工具的`x-object-id` header

**预期结果**：
```python
obj1_query() → x-object-id: obj1  # ✅ 正确
obj2_query() → x-object-id: obj2  # ✅ 正确
obj3_query() → x-object-id: obj3  # ✅ 正确
# ❌ 不应该都是 obj3（闭包陷阱）
```

**验证点**：
- ✅ 每个工具引用正确的object_code
- ✅ 没有闭包变量捕获问题

---

### 3.2 模式2：动态Tool加载模式

#### 3.2.1 设计说明
Worker启动时，为每个`mounted_object`自动生成`{本体名称}_query`方法，并可选地加载本体定义的tool，动态注册到Deep Agent中。

#### 3.2.2 配置方式
```bash
# 环境变量配置
ONTOLOGY_LOAD_MODE=dynamic_tool
ONTOLOGY_SCENE_PATH=/path/to/owl/directory  # 本体OWL文件目录
ONTOLOGY_AUTO_REGISTER=true  # 是否自动注册本体定义的tool
```

**说明**：
- `mounted_objects`由`init_agent_conf.py`自动提取，无需配置
- `ONTOLOGY_SCENE_PATH`指向OWL本体定义文件的目录

#### 3.2.3 实现方案

**动态工具生成器实现**：

**文件**：`src/datacloud_analysis/ontology/dynamic_tool_generator.py`

```python
"""动态工具生成器 - 模式2"""
from typing import Any
from langchain_core.tools import tool


def generate_dynamic_tools(
    mounted_objects: list[str],
    scene_path: str,
    auto_register_tools: bool = True
) -> list[Any]:
    """为mounted_objects生成动态工具
    
    Args:
        mounted_objects: 挂载的对象列表
        scene_path: OWL文件目录路径
        auto_register_tools: 是否自动注册action工具
    
    Returns:
        动态工具列表
    """
    from datacloud_data_sdk.ontology.loader import OntologyLoader
    
    # 1. 加载本体定义
    loader = OntologyLoader()
    if scene_path:
        loader.load_from_owl_directory(scene_path)
    
    tools = []
    
    for object_code in mounted_objects:
        # 2. 生成 {object_code}_query 工具
        query_tool = _generate_query_tool(object_code, loader)
        tools.append(query_tool)
        
        # 3. 可选：加载本体定义的action工具
        if auto_register_tools:
            try:
                onto_class = loader.get_ontology_class(object_code)
                if onto_class and onto_class.actions:
                    for action in onto_class.actions:
                        action_tool = _generate_action_tool(object_code, action, loader)
                        tools.append(action_tool)
            except Exception as e:
                # 如果本体定义不存在或加载失败，跳过action工具生成
                import logging
                logging.warning(f"无法为{object_code}生成action工具: {e}")
    
    return tools


def _generate_query_tool(object_code: str, loader):
    """为本体对象生成query工具
    
    注意：此工具是对现有query_objects的封装，只是固定了object_type参数
    """
    
    @tool
    async def query_tool(
        question: str = None,
        filters: dict = None,
        fields: list[str] = None,
        limit: int = 100,
    ) -> dict:
        f"""查询{object_code}对象数据
        
        Args:
            question: 自然语言查询问题（可选）
            filters: 结构化过滤条件（可选）
            fields: 返回字段列表（可选）
            limit: 返回数量限制
        
        Returns:
            查询结果
        """
        # 直接调用底层query_objects，固定object_type
        from datacloud_analysis.tools.oql.query_objects import query_objects
        
        return await query_objects(
            object_type=object_code,
            question=question,
            filters=filters,
            fields=fields,
            limit=limit,
        )
    
    # 设置工具名称
    query_tool.__name__ = f"{object_code}_query"
    query_tool.name = f"{object_code}_query"
    query_tool.description = f"查询{object_code}对象数据"
    
    return query_tool


def _generate_action_tool(object_code: str, action, loader):
    """为本体定义的action生成工具
    
    注意：此工具是对现有execute_action的封装，固定了action_type和target_objects参数
    """
    
    @tool
    async def action_tool(**kwargs) -> dict:
        f"""{action.action_name or action.action_code}
        
        {action.description or ''}
        """
        # 直接调用底层execute_action
        from datacloud_analysis.tools.oql.execute_action import execute_action
        
        return await execute_action(
            action_type=action.action_code,
            target_objects=[object_code],
            payload=kwargs
        )
    
    # 设置工具名称
    action_tool.__name__ = f"{object_code}_{action.action_code}"
    action_tool.name = f"{object_code}_{action.action_code}"
    action_tool.description = action.description or action.action_name or f"执行{action.action_code}动作"
    
    return action_tool
```

#### 3.2.4 使用示例
```python
# Agent调用示例（LLM视角）

# 1. 调用自动生成的query方法
result = await ads_grid_analysis_query(
    question="查询华东地区的广告网格",
    limit=50
)

# 或使用结构化查询
result = await ads_grid_analysis_query(
    filters={"region": "华东"},
    fields=["grid_id", "coverage"],
    limit=50
)

# 2. 调用本体定义的action工具（如果auto_register=true）
result = await ads_grid_analysis_analyze_performance(
    grid_id="grid_001",
    metrics=["coverage", "signal_strength"]
)
```

#### 3.2.5 调用流程

```
Agent调用
  ↓
LLM选择工具：ads_grid_analysis_query(question="...")
  ↓
动态生成的本地工具被调用
  ↓
调用底层query_objects(object_type="ads_grid_analysis", question="...")
  ↓
query_objects通过HTTP调用datacloud-data服务
  ↓
返回查询结果给Agent
```

#### 3.2.6 特点
- ✅ 工具名称明确，每个对象有专属工具（如`ads_grid_analysis_query`）
- ✅ 降低LLM选择工具的复杂度（不需要理解object_type参数）
- ✅ 支持自动注册本体定义的actions
- ✅ 不支持固定的Query、Action方法（模式2特点）
- ✅ 实际执行仍通过query_objects调用datacloud-data服务（与模式3相同）
- ✅ 启动时加载OWL定义用于生成工具，但不影响运行时性能
- ❌ Worker启动时需加载本体OWL定义（启动稍慢）
- ❌ 工具数量可能很多（对象数 × 1+action数）

#### 3.2.7 适用场景
- 本体数量适中（< 20个）
- 希望工具名称明确，降低LLM理解成本
- 本体定义了丰富的action工具
- 需要类型安全和参数校验
- 不介意启动时加载OWL定义的开销

#### 3.2.8 验收测试用例

##### 测试用例1：验证动态工具生成
**前置条件**：
- 环境变量：`ONTOLOGY_LOAD_MODE=dynamic_tool`
- 环境变量：`ONTOLOGY_SCENE_PATH=/path/to/owl/`
- 环境变量：`ONTOLOGY_AUTO_REGISTER=true`
- `mounted_objects = ["ads_grid_analysis"]`
- OWL定义包含1个action：`analyze_performance`

**测试步骤**：
1. 创建agent
2. 检查注册的工具列表

**预期结果**：
```python
tools = [
    ads_grid_analysis_query,  # ✅ 已生成
    ads_grid_analysis_analyze_performance,  # ✅ 已生成（action工具）
]
# ❌ 不包含 query_objects
# ❌ 不包含 execute_action
```

**验证点**：
- ✅ 生成query工具
- ✅ 生成action工具（auto_register=true）
- ✅ 不注册通用工具

---

##### 测试用例2：验证动态工具调用query_objects
**前置条件**：
- Agent已创建（模式2）

**测试步骤**：
1. LLM调用工具：
```python
ads_grid_analysis_query(
    question="查询华东地区的网格",
    limit=10
)
```
2. 使用mock或spy检查内部调用

**预期结果**：
```python
# 内部调用
query_objects(
    object_type="ads_grid_analysis",
    question="查询华东地区的网格",
    limit=10
)
```

**验证点**：
- ✅ 动态工具内部调用`query_objects`
- ✅ `object_type`参数已固定
- ✅ 其他参数正确传递

---

##### 测试用例3：验证auto_register=false
**前置条件**：
- 环境变量：`ONTOLOGY_AUTO_REGISTER=false`
- `mounted_objects = ["ads_grid_analysis"]`

**测试步骤**：
1. 创建agent
2. 检查注册的工具列表

**预期结果**：
```python
tools = [
    ads_grid_analysis_query,  # ✅ 已生成
    execute_action,  # ✅ 保留通用action工具
]
# ❌ 不包含 ads_grid_analysis_analyze_performance
# ❌ 不包含 query_objects
```

**验证点**：
- ✅ 不生成action工具
- ✅ 保留`execute_action`作为通用入口

---

on工具（auto_register=true）
- ✅ 不注册通用工具

---

##### 测试用例2：验证动态工具调用query_objects
**前置条件**：
- Agent已创建（模式2）

**测试步骤**：
1. LLM调用工具：
```python
ads_grid_analysis_query(
    question="查询华东地区的网格",
    limit=10
)
```
2. 使用mock或spy检查内部调用

**预期结果**：
```python
# 内部调用
query_objects(
    object_type="ads_grid_analysis",
    question="查询华东地区的网格",
    limit=10
)
```

**验证点**：
- ✅ 动态工具内部调用`query_objects`
- ✅ `object_type`参数已固定
- ✅ 其他参数正确传递

---

##### 测试用例3：验证auto_register=false
**前置条件**：
- 环境变量：`ONTOLOGY_AUTO_REGISTER=false`
- `mounted_objects = ["ads_grid_analysis"]`

**测试步骤**：
1. 创建agent
2. 检查注册的工具列表

**预期结果**：
```python
tools = [
    ads_grid_analysis_query,  # ✅ 已生成
    execute_action,  # ✅ 保留通用action工具
]
# ❌ 不包含 ads_grid_analysis_analyze_performance
# ❌ 不包含 query_objects
```

**验证点**：
- ✅ 不生成action工具
- ✅ 保留`execute_action`作为通用入口

---

### 3.3 模式3：统一接口模式（当前实现）

#### 3.3.1 设计说明
不为每个本体生成专属工具，而是通过固定的`Query`和`Action`两个通用方法，在调用时通过参数指定本体对象来执行。这是最轻量的模式，也是当前的实现方式。

#### 3.3.2 配置方式
```bash
# 环境变量配置
ONTOLOGY_LOAD_MODE=unified_interface  # 或不设置（默认值）
```

**说明**：
- `mounted_objects`由`init_agent_conf.py`自动提取
- 只注册`query_objects`和`execute_action`两个固定工具
- 通过`KnowledgeInjectionMiddleware`注入本体Schema到LLM上下文

#### 3.3.3 实现方案（当前架构）

**Agent创建**（无需修改）：
```python
# src/datacloud_analysis/agent.py

def create_agent(
    mounted_objects: list[str] | None = None,
    tools: dict[str, Any] | None = None,
    ...
):
    """创建agent - 当前实现"""
    
    # 1. 注册核心OQL工具（固定2个）
    all_tools = register_all_tools()  # [query_objects, execute_action]
    
    # 2. 添加其他工具（AGENT委托等）
    if tools:
        all_tools.extend(tools.values())
    
    # 3. 创建中间件，注入本体知识
    middlewares = [
        KnowledgeInjectionMiddleware(mounted_objects=mounted_objects),
        ...
    ]
    
    # 4. 创建Deep Agent
    return _create_deep_agent(
        tools=all_tools,
        middleware=middlewares,
        mounted_objects=mounted_objects,
        ...
    )
```

**KnowledgeInjectionMiddleware**（当前实现）：
```python
# src/datacloud_analysis/middlewares/knowledge_injection.py

class KnowledgeInjectionMiddleware(AgentMiddleware):
    """在每次LLM调用前注入本体Schema"""
    
    def __init__(self, mounted_objects: list[str] | None = None):
        self.mounted_objects = mounted_objects or []
    
    async def awrap_model_call(self, request: ModelRequest, handler):
        """注入本体Schema到system message"""
        
        if not self.mounted_objects:
            return await handler(request)
        
        # 1. 加载本体定义
        loader = OntologyLoader()
        scene_path = self._resolve_scene_path()
        loader.load_from_owl_directory(scene_path)
        
        # 2. 构建Schema
        schema_lines = ["<ontology_context>"]
        schema_lines.append("## 可用对象类型\n")
        schema_lines.append("要查询以下对象的数据，请使用 `query_objects` 工具。")
        schema_lines.append("调用方式：`query_objects(object_type=\"对象编码\", filters={...}, ...)`\n")
        
        for object_code in self.mounted_objects:
            onto_class = loader.get_ontology_class(object_code)
            formatted = format_object_schema(onto_class, loader)
            schema_lines.append(formatted)
        
        schema_lines.append("</ontology_context>")
        schema = "\n".join(schema_lines)
        
        # 3. 注入到system message
        updated_request = request.override(
            system_message=append_to_system_message(
                request.system_message,
                schema
            )
        )
        
        return await handler(updated_request)
```

**固定Query工具**（当前实现）：
```python
# src/datacloud_analysis/tools/oql/query_objects.py

@tool
def query_objects(
    object_type: str,  # 对象编码，如 "ads_grid_analysis"
    select: list[str] = None,
    where: list[dict] = None,
    limit: int = 100,
    offset: int = 0,
    ...
) -> dict:
    """查询本体对象或视图的实例列表
    
    Args:
        object_type: 对象类型名（必须来自本体注册表）
        select: 返回属性列表
        where: 过滤条件数组
        limit: 返回记录数上限
        offset: 分页偏移量
    
    Returns:
        查询结果
    """
    router = get_oql_router()
    records = await router.route(
        oql_params={
            "object": object_type,
            "fields": select,
            "where": where,
            "limit": limit,
            "offset": offset,
        },
        ...
    )
    return format_oql_response(records=records, ...)
```

**固定Action工具**（当前实现）：
```python
# src/datacloud_analysis/tools/oql/execute_action.py

@tool
def execute_action(
    action_type: str,
    target_objects: list[str],
    payload: dict = None,
    ...
) -> dict:
    """执行本体定义的动作
    
    Args:
        action_type: 动作类型编码
        target_objects: 目标对象列表
        payload: 动作参数
    
    Returns:
        执行结果
    """
    router = get_oql_router()
    result = await router.execute_action(
        action_type=action_type,
        target_objects=target_objects,
        payload=payload,
        ...
    )
    return format_action_response(result=result, ...)
```

#### 3.3.4 使用示例
```python
# Agent调用示例（LLM视角）

# 1. 查询本体对象
result = await query_objects(
    object_type="ads_grid_analysis",
    where=[{"field": "region", "op": "eq", "value": "华东"}],
    select=["grid_id", "coverage"],
    limit=50
)

# 2. 执行本体动作
result = await execute_action(
    action_type="analyze_performance",
    target_objects=["ads_grid_analysis"],
    payload={"grid_id": "grid_001", "metrics": ["coverage"]}
)
```

#### 3.3.5 调用流程

```
Agent调用
  ↓
LLM选择工具：query_objects(object_type="ads_grid_analysis", ...)
  ↓
固定的query_objects工具被调用
  ↓
通过HTTP调用datacloud-data服务
  ↓
返回查询结果给Agent
```

#### 3.3.6 特点
- ✅ 工具数量固定（2个），启动最快
- ✅ 内存占用最小
- ✅ 支持固定的Query、Action方法（模式3特点）
- ✅ 通过中间件注入Schema，LLM理解本体结构
- ✅ 当前已实现，稳定可靠
- ❌ LLM需要理解object_type参数
- ❌ 工具名称不够直观

#### 3.3.7 适用场景
- 本体数量较多（> 20个）
- 追求最小内存占用和最快启动速度
- 现有系统，需要向后兼容
- 不介意LLM需要理解object_type参数

#### 3.3.8 验收测试用例

##### 测试用例1：验证固定工具注册
**前置条件**：
- 环境变量：`ONTOLOGY_LOAD_MODE=unified_interface`（或不设置）
- `mounted_objects = ["ads_grid_analysis", "customer_analysis"]`

**测试步骤**：
1. 创建agent
2. 检查注册的工具列表

**预期结果**：
```python
tools = [
    query_objects,  # ✅ 已注册
    execute_action,  # ✅ 已注册
]
# ❌ 不包含 ads_grid_analysis_query
# ❌ 不包含 customer_analysis_query
```

**验证点**：
- ✅ 只注册2个固定工具
- ✅ 不生成专属工具

---

##### 测试用例2：验证query_objects调用
**前置条件**：
- Agent已创建
- datacloud-data服务运行中

**测试步骤**：
1. LLM调用工具：
```python
query_objects(
    object_type="ads_grid_analysis",
    where=[{"field": "region", "op": "eq", "value": "华东"}],
    limit=10
)
```
2. 检查HTTP请求

**预期结果**：
- ✅ 发起HTTP POST到datacloud-data服务
- ✅ 返回查询结果

---

t
2. 检查注册的工具列表

**预期结果**：
```python
tools = [
    query_objects,  # ✅ 已注册
    execute_action,  # ✅ 已注册
]
# ❌ 不包含 ads_grid_analysis_query
# ❌ 不包含 customer_analysis_query
```

**验证点**：
- ✅ 只注册2个固定工具
- ✅ 不生成专属工具

---

##### 测试用例2：验证Schema注入
**前置条件**：
- Agent已创建（模式3）
- `mounted_objects = ["ads_grid_analysis"]`

**测试步骤**：
1. 触发LLM调用
2. 检查system message

**预期结果**：
```
system message包含：
<ontology_context>
## 可用对象类型
要查询以下对象的数据，请使用 `query_objects` 工具。
调用方式：`query_objects(object_type="对象编码", filters={...}, ...)`

### ads_grid_analysis
- 属性：grid_id, region, coverage, ...
- 动作：analyze_performance, ...
</ontology_context>
```

**验证点**：
- ✅ Schema已注入到system message
- ✅ 包含所有mounted_objects的定义

---

##### 测试用例3：验证query_objects调用
**前置条件**：
- Agent已创建
- datacloud-data服务运行中

**测试步骤**：
1. LLM调用工具：
```python
query_objects(
    object_type="ads_grid_analysis",
    where=[{"field": "region", "op": "eq", "value": "华东"}],
    limit=10
)
```
2. 检查HTTP请求

**预期结果**：
- ✅ 发起HTTP POST到datacloud-data服务
- ✅ 返回查询结果

---


## 4. 三种模式对比

| 维度 | 模式1：MCP模式 | 模式2：动态Tool加载 | 模式3：统一接口（当前） |
|------|---------------|-------------------|----------------|
| **注册的工具** | {对象}_query×N | {对象}_query×N<br>+ {对象}_{action}×M（可选） | query_objects<br>+ execute_action |
| **工具总数** | 对象数×1 | 对象数×(1+action数) | 固定2个 |
| **工具名称示例** | ads_grid_analysis_query | ads_grid_analysis_query<br>ads_grid_analysis_analyze | query_objects<br>execute_action |
| **LLM调用示例** | ads_grid_analysis_query(question="...") | ads_grid_analysis_query(filters={...}) | query_objects(object_type="ads_grid_analysis", ...) |
| **启动速度** | 快（只生成工具定义） | 慢（需加载OWL定义） | 最快（无额外加载） |
| **内存占用** | 小 | 中（OWL定义常驻） | 最小 |
| **查询执行** | MCP协议→datacloud-data | query_objects→datacloud-data | query_objects→datacloud-data |
| **执行性能** | 中（MCP协议开销） | 高（直接HTTP调用） | 高（直接HTTP调用） |
| **类型安全** | 中（动态生成） | 高（基于OWL定义） | 低（参数传递） |
| **固定Query/Action** | 否 | 否 | 是 |
| **本体发现** | 自动（init_agent_conf.py） | 自动（init_agent_conf.py） | 自动（init_agent_conf.py） |
| **Schema注入** | 可选（通过中间件） | 可选（通过中间件） | 是（KnowledgeInjectionMiddleware） |
| **适用对象数** | 不限 | < 20 | > 20 |
| **部署复杂度** | 中（需MCP服务） | 低（单机） | 低（单机） |
| **扩展性** | 高 | 中 | 低 |
| **当前状态** | 需实现 | 需实现 | ✅ 已实现 |

**关键差异**：
- **模式1**：为每个对象生成专属工具（`{对象}_query`），通过MCP协议调用datacloud-data，**不注册**`query_objects`
- **模式2**：为每个对象生成专属工具（`{对象}_query`和可选的action工具），直接调用`query_objects`（底层HTTP），**不注册**`query_objects`
- **模式3**：**只注册**`query_objects`和`execute_action`，不生成专属工具

**三种模式的查询执行路径**：
- **模式1**：`{对象}_query` → MCP协议 → datacloud-data MCP handler → 查询执行
- **模式2**：`{对象}_query` → `query_objects` → datacloud-data HTTP API → 查询执行
- **模式3**：`query_objects` → datacloud-data HTTP API → 查询执行

**核心区别**：
- 模式1和模式2的区别在于**工具接口层**（MCP vs 直接HTTP）
- 模式2和模式3的区别在于**工具粒度**（专属工具 vs 通用工具）
- 三种模式的**查询执行**都在datacloud-data服务端完成

**为什么模式1/2不注册query_objects**：
- 已经为每个对象生成了专属工具，LLM直接调用专属工具即可
- 避免工具冗余和LLM选择困惑
- 专属工具名称更明确，LLM更容易理解和选择


## 5. 开发实现

本章说明如何实现三种模式的通用基础设施。各模式的具体工具生成器代码已在第3章给出。

### 5.1 文件结构

需要创建以下文件来支持三种模式：

```
src/datacloud_analysis/
├── config/
│   └── ontology_settings.py          # 本体配置类（新增）
├── ontology/
│   ├── __init__.py                   # 新增目录
│   ├── mode_loader.py                # 模式加载器（新增）
│   ├── mcp_tool_generator.py         # 模式1工具生成器（新增，代码见3.1.3）
│   └── dynamic_tool_generator.py     # 模式2工具生成器（新增，代码见3.2.3）
├── agent.py                          # Agent创建入口（需修改）
└── tools/
    └── oql/
        ├── query_objects.py          # 已存在
        └── execute_action.py         # 已存在
```

**说明**：
- `mcp_tool_generator.py` 和 `dynamic_tool_generator.py` 的具体实现代码已在第3章各模式的"实现方案"小节中给出
- 本章重点说明跨模式的通用基础设施

---

### 5.2 配置类实现

**文件**：`src/datacloud_analysis/config/ontology_settings.py`

```python
"""本体加载配置"""
from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OntologySettings(BaseSettings):
    """本体加载配置
    
    通过环境变量配置：
    - ONTOLOGY_LOAD_MODE: 加载模式
    - ONTOLOGY_MCP_ENDPOINT: MCP服务端点（模式1必需）
    - ONTOLOGY_SCENE_PATH: OWL文件目录（模式2必需）
    - ONTOLOGY_AUTO_REGISTER: 是否自动注册action工具（模式2可选）
    """
    
    model_config = SettingsConfigDict(
        env_prefix="ONTOLOGY_",
        extra="ignore"
    )
    
    load_mode: Literal["mcp", "dynamic_tool", "unified_interface"] = Field(
        default="unified_interface",
        description="本体加载模式：mcp | dynamic_tool | unified_interface"
    )
    
    # 模式1：MCP配置
    mcp_endpoint: Optional[str] = Field(
        default=None,
        description="MCP服务端点，例如：http://datacloud-data:8080/api/v1/mcp/"
    )
    
    # 模式2：动态Tool配置
    scene_path: Optional[str] = Field(
        default=None,
        description="本体OWL文件目录路径，例如：/app/ontology/owl"
    )
    
    auto_register: bool = Field(
        default=True,
        description="是否自动注册本体定义的action工具（仅模式2）"
    )
```

---

### 5.3 模式加载器实现

**文件**：`src/datacloud_analysis/ontology/mode_loader.py`

```python
"""本体模式加载器"""
from typing import Any
from datacloud_analysis.config.ontology_settings import OntologySettings


class OntologyModeLoader:
    """本体模式加载器
    
    根据配置的模式，为mounted_objects生成相应的工具。
    具体工具生成器的实现代码见第3章各模式的"实现方案"小节。
    """
    
    def __init__(self, settings: OntologySettings = None):
        """初始化
        
        Args:
            settings: 本体配置，如果为None则从环境变量加载
        """
        self.settings = settings or OntologySettings()
        self.mode = self.settings.load_mode
    
    def generate_tools(self, mounted_objects: list[str]) -> list[Any]:
        """根据模式为mounted_objects生成工具
        
        Args:
            mounted_objects: 由init_agent_conf.py自动提取的对象列表
        
        Returns:
            工具列表
        
        Raises:
            ValueError: 未知的加载模式或缺少必需配置
        """
        if not mounted_objects:
            return []
        
        if self.mode == "mcp":
            if not self.settings.mcp_endpoint:
                raise ValueError("模式1（MCP）需要配置 ONTOLOGY_MCP_ENDPOINT 环境变量")
            return self._generate_mcp_tools(mounted_objects)
        
        elif self.mode == "dynamic_tool":
            if not self.settings.scene_path:
                raise ValueError("模式2（动态Tool）需要配置 ONTOLOGY_SCENE_PATH 环境变量")
            return self._generate_dynamic_tools(mounted_objects)
        
        elif self.mode == "unified_interface":
            return []  # 使用固定的query_objects/execute_action
        
        else:
            raise ValueError(f"未知的本体加载模式: {self.mode}")
    
    def _generate_mcp_tools(self, mounted_objects: list[str]) -> list[Any]:
        """模式1：为每个对象生成MCP工具
        
        具体实现见 3.1.3 实现方案
        """
        from datacloud_analysis.ontology.mcp_tool_generator import generate_mcp_tools
        
        return generate_mcp_tools(
            endpoint=self.settings.mcp_endpoint,
            mounted_objects=mounted_objects
        )
    
    def _generate_dynamic_tools(self, mounted_objects: list[str]) -> list[Any]:
        """模式2：为每个对象生成动态工具
        
        具体实现见 3.2.3 实现方案
        """
        from datacloud_analysis.ontology.dynamic_tool_generator import generate_dynamic_tools
        
        return generate_dynamic_tools(
            mounted_objects=mounted_objects,
            scene_path=self.settings.scene_path,
            auto_register_tools=self.settings.auto_register
        )
```

---

### 5.4 Agent集成

**文件**：`src/datacloud_analysis/agent.py`（修改现有文件）

```python
"""Agent创建入口"""
from typing import Any
from datacloud_analysis.config.ontology_settings import OntologySettings
from datacloud_analysis.ontology.mode_loader import OntologyModeLoader


def create_agent(
    mounted_objects: list[str] | None = None,  # 由init_agent_conf.py传入
    tools: dict[str, Any] | None = None,
    **kwargs
):
    """创建agent
    
    Args:
        mounted_objects: 挂载的对象列表（由init_agent_conf.py自动提取）
        tools: 其他工具（AGENT委托等）
        **kwargs: 其他参数
    
    Returns:
        创建的agent实例
    """
    all_tools = []
    
    # 1. 根据模式决定注册哪些工具
    ontology_settings = OntologySettings()
    ontology_loader = OntologyModeLoader(ontology_settings)
    mode = ontology_settings.load_mode
    
    if mode == "unified_interface":
        # 模式3：只注册固定的OQL工具
        from datacloud_analysis.tools.oql import register_all_tools
        all_tools = register_all_tools()  # [query_objects, execute_action]
    
    elif mode in ("mcp", "dynamic_tool"):
        # 模式1/2：为每个对象生成专属工具
        if mounted_objects:
            ontology_tools = ontology_loader.generate_tools(mounted_objects)
            all_tools.extend(ontology_tools)
        
        # 可选：保留execute_action作为通用action入口
        # （如果模式2的auto_register=false，或者需要执行未定义的action）
        if mode == "dynamic_tool" and not ontology_settings.auto_register:
            from datacloud_analysis.tools.oql.execute_action import execute_action
            all_tools.append(execute_action)
    
    # 2. 添加其他工具（AGENT委托等）
    if tools:
        all_tools.extend(tools.values())
    
    # 3. 创建middlewares（模式3需要KnowledgeInjectionMiddleware）
    middlewares = []
    if mode == "unified_interface" and mounted_objects:
        from datacloud_analysis.middlewares.knowledge_injection import KnowledgeInjectionMiddleware
        middlewares.append(KnowledgeInjectionMiddleware(mounted_objects=mounted_objects))
    
    # 4. 创建agent
    from deepagents import create_deep_agent
    
    agent = create_deep_agent(
        tools=all_tools,
        middleware=middlewares,
        **kwargs
    )
    
    return agent
```

---

### 5.5 环境变量配置示例

**模式3（统一接口，默认）**：
```bash
# 不设置或显式设置
ONTOLOGY_LOAD_MODE=unified_interface
```

**模式1（MCP）**：
```bash
ONTOLOGY_LOAD_MODE=mcp
ONTOLOGY_MCP_ENDPOINT=http://datacloud-data-service:8080/api/v1/mcp/
```

**模式2（动态Tool）**：
```bash
ONTOLOGY_LOAD_MODE=dynamic_tool
ONTOLOGY_SCENE_PATH=/app/ontology/owl
ONTOLOGY_AUTO_REGISTER=true  # 或 false
```

**说明**：
- 地址和路径应根据实际部署环境配置
- `ONTOLOGY_MCP_ENDPOINT`：指向datacloud-data服务的MCP端点
- `ONTOLOGY_SCENE_PATH`：指向OWL本体定义文件的目录

---

## 6. 使用指南

### 6.1 环境变量配置

**模式3（统一接口，默认）**：
```bash
# 不设置或显式设置
ONTOLOGY_LOAD_MODE=unified_interface
```

**模式1（MCP）**：
```bash
ONTOLOGY_LOAD_MODE=mcp
ONTOLOGY_MCP_ENDPOINT=http://datacloud-data-service:8080/api/v1/mcp/
```

**模式2（动态Tool）**：
```bash
ONTOLOGY_LOAD_MODE=dynamic_tool
ONTOLOGY_SCENE_PATH=/app/ontology/owl
ONTOLOGY_AUTO_REGISTER=true  # 或 false
```

**说明**：
- 地址和路径应根据实际部署环境配置
- `ONTOLOGY_MCP_ENDPOINT`：指向datacloud-data服务的MCP端点
- `ONTOLOGY_SCENE_PATH`：指向OWL本体定义文件的目录

---

### 6.2 模式切换

#### 从模式3切换到模式1（MCP）

**适用场景**：需要独立部署本体服务，或与其他MCP生态集成

**操作步骤**：
1. 确保datacloud-data MCP服务已部署并运行
2. 设置环境变量：
   ```bash
   ONTOLOGY_LOAD_MODE=mcp
   ONTOLOGY_MCP_ENDPOINT=http://datacloud-data-service:8080/api/v1/mcp/
   ```
3. 重启Worker
4. 验证工具列表（应包含`{对象}_query`，不包含`query_objects`）

**注意事项**：
- 需要确保MCP服务可访问
- 工具数量会增加（每个对象一个工具）
- LLM prompt可能需要调整（工具名称变化）

---

#### 从模式3切换到模式2（动态Tool）

**适用场景**：希望降低LLM理解成本，本体数量适中

**操作步骤**：
1. 确保OWL定义文件可访问
2. 设置环境变量：
   ```bash
   ONTOLOGY_LOAD_MODE=dynamic_tool
   ONTOLOGY_SCENE_PATH=/app/ontology/owl
   ONTOLOGY_AUTO_REGISTER=true  # 可选
   ```
3. 重启Worker
4. 验证工具列表（应包含`{对象}_query`和action工具）

**注意事项**：
- 启动时间会增加（需加载OWL）
- 内存占用会增加
- 工具数量会显著增加（对象数 × (1+action数)）

---

#### 回退到模式3

**操作步骤**：
1. 删除或注释环境变量：
   ```bash
   # ONTOLOGY_LOAD_MODE=mcp
   # ONTOLOGY_MCP_ENDPOINT=...
   ```
   或设置为默认值：
   ```bash
   ONTOLOGY_LOAD_MODE=unified_interface
   ```
2. 重启Worker
3. 验证工具列表（应只包含`query_objects`和`execute_action`）

---


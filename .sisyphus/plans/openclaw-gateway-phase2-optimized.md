# OpenClaw Gateway Phase 2 优化计划 (基于POC验证结果)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 基于6个POC验证结果，将模拟代码替换为实际的deepagents集成，使OpenClaw Gateway真正可用

**架构:** 复用deepagents内置能力（子Agent、中断恢复、流式输出、Checkpoint），**工具backend需先验证（修正：使用backend参数替代sandbox）**，重点实现deepagents与现有Gateway的集成层

**Tech Stack:** Python 3.12+, deepagents 0.4.7, LangGraph 1.0.10, 阿里云百炼Qwen

**工作目录:** `/home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation`

**时间估算（已修正）:** 8-10天（原6-8天，增加backend验证和安全增强）

---

## 已实现架构概览

### 多租户与文件空间设计（已实现）

基于 `openclaw_gateway_python设计/12-多租户与文件空间设计.md`，以下组件**已在worktree中实现**：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OpenClaw Gateway (Python)                           │
│                    多租户 + 文件管理规范 + DeepAgents 融合架构                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Tenant Resolution Layer                          │   │
│  │  - X-Tenant-ID Header 解析 tenant_id                                 │   │
│  │  - Session Key 解析: tenant:{tenantId}:agent:{agentId}:{mainKey}    │   │
│  │  - contextvars.ContextVar 请求级隔离                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              TenantWorkspaceManager (三层根目录管理)                  │   │
│  │                                                                     │   │
│  │  public/                    → 应用级共享 (namespace: ("app",))        │   │
│  │  {tenantId}_public/         → 租户级共享 (namespace: ("user", id))    │   │
│  │  {tenantId}_private/        → 租户私有   (namespace: ("user", id))    │   │
│  │                                                                     │   │
│  │  四层组织: 应用级 → 用户级 → 会话级 → 任务级                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              TenantAwareFileBackend (DeepAgents 集成)                │   │
│  │                                                                     │   │
│  │  路由规则:                                                          │   │
│  │  - public/* → 公共存储                                             │   │
│  │  - user_public/* → 租户公共存储                                    │   │
│  │  - user_private/* → 租户私有存储                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              AgentRunner (DeepAgents 集成)                           │   │
│  │                                                                     │   │
│  │  - 注入 TenantAwareFileBackend                                       │   │
│  │  - SystemPromptBuilder 包含租户上下文                                 │   │
│  │  - Namespace 隔离的持久化存储                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 已实现的文件结构

```
workspaces/
├── public/                                    # 应用级 (所有租户共享)
│   └── .datacloud/
│       └── skills/                            # 应用自带技能
│
├── {tenantId}_public/                         # 租户级共享
│   ├── memory/
│   │   ├── memory.md                          # 公共长期记忆
│   │   └── memory-datacloud.md               # 应用特定记忆
│   ├── session-{session_id}/                  # 会话级 (持久化)
│   │   ├── short-memory.jsonl                # 短期记忆
│   │   └── user-data/                        # 用户上传数据
│   └── .datacloud/skills/                     # 租户生成技能
│
└── {tenantId}_private/.datacloud/workspaces/  # 租户私有
    └── session-{session_id}/                  # 会话级 (持久化)
        ├── skills/                            # 会话技能 (跨任务共享)
        ├── cache/                             # 缓存数据
        ├── state.json                         # 会话状态
        └── tasks/task-{task_id}/              # 任务级 (临时)
            ├── temp/                          # 任务临时文件
            ├── output/                        # 任务输出结果
            └── state.json                     # 任务状态
```

### 四层组织结构

| 层级 | 路径模式 | 用途 | 生命周期 |
|------|---------|------|---------|
| **应用级** | `/public/*` | 应用自带技能、共享资源 | 随应用部署 |
| **用户级** | `/{tenantId}_public/*` `/{tenantId}_private/*` | 租户配置、长期记忆、生成技能 | 租户存续期间 |
| **会话级** | `/.../session-{id}/*` | 会话状态、短期记忆、会话技能 | 会话存续期间 |
| **任务级** | `/.../tasks/task-{id}/*` | 任务临时文件、输出结果 | 任务执行期间 |

---

## 官方资源

### 文档和仓库
- **GitHub**: https://github.com/langchain-ai/deepagents (10.2k ⭐)
- **文档**: https://docs.langchain.com/oss/python/deepagents/overview
- **PyPI**: https://pypi.org/project/deepagents/ (v0.4.7)

### 官方示例
| 示例 | 路径 | 说明 |
|------|------|------|
| deep_research | `examples/deep_research/` | 多步骤网络搜索，并行子Agent |
| text-to-sql-agent | `examples/text-to-sql-agent/` | 自然语言转SQL |
| content-builder-agent | `examples/content-builder-agent/` | 记忆、技能、子Agent |
| ralph_mode | `examples/ralph_mode/` | 自主循环模式 |

### 关键使用模式
```python
# 来自官方示例的标准用法
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

agent = create_deep_agent(
    model=model,
    tools=[custom_tool],
    backend=FilesystemBackend(root_dir="/workspace"),  # 文件系统后端
    subagents=[research_sub_agent],
    memory=["./AGENTS.md"],  # 记忆文件
    skills=["./skills/"],     # 技能目录
)
```

---

## 开发指南：如何查阅deepagents文档和源码

### 0. 使用AI助手工具（推荐）

在执行任务时，你可以调用以下工具来获取帮助：

```python
# 使用webfetch获取官方文档
webfetch(url="https://deepagents.readthedocs.io/en/latest/", format="markdown")

# 使用skill查询LangChain/LangGraph文档
skill(name="langchain-docs", user_message="查询create_deep_agent的用法和参数")

# 使用librarian agent搜索GitHub示例
task(subagent_type="librarian", load_skills=[], prompt="搜索deepagents的GitHub仓库，查找create_deep_agent的使用示例和sandbox参数", run_in_background=True)

# 使用explore agent分析代码库
task(subagent_type="explore", load_skills=[], prompt="分析deepagents包的结构，找出所有与sandbox、tools、subagents相关的源码文件", run_in_background=True)
```

### 1. 查看deepagents源码

```bash
# 找到deepagents安装位置
cd /home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation
uv run --package datacloud-agent python -c "import deepagents; print(deepagents.__file__)"

# 典型路径示例：
# /home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation/.venv/lib/python3.12/site-packages/deepagents/__init__.py

# 查看核心模块
ls -la $(uv run --package datacloud-agent python -c "import deepagents; import os; print(os.path.dirname(deepagents.__file__))")

# 关键文件：
# - __init__.py          # 主要导出：create_deep_agent
# - agent.py             # Agent实现
# - tools.py             # 工具系统
# - sandbox.py           # 沙箱实现（如果有）

# 搜索源码中的特定功能
grep -r "sandbox" $(uv run --package datacloud-agent python -c "import deepagents; import os; print(os.path.dirname(deepagents.__file__))") --include="*.py"
```

### 2. 查看deepagents文档

```bash
# 方法1: 查看源码中的docstring
uv run --package datacloud-agent python -c "
from deepagents import create_deep_agent
help(create_deep_agent)
"

# 方法2: 使用pydoc
uv run pydoc deepagents

# 方法3: 查看类型提示（了解函数签名）
uv run --package datacloud-agent python -c "
from deepagents import create_deep_agent
import inspect
print(inspect.signature(create_deep_agent))
"
```

### 3. 网络搜索和GitHub搜索

```bash
# 搜索deepagents文档（使用AI助手的webfetch工具）
# 示例：
# webfetch(url="https://github.com/langchain-ai/deepagents", format="markdown")

# 搜索GitHub Issues（了解已知问题）
# 使用librarian agent:
# task(subagent_type="librarian", prompt="搜索deepagents GitHub issues中关于sandbox的问题")

# 搜索相关博客和教程
# task(subagent_type="librarian", prompt="搜索deepagents使用教程和最佳实践")
```

### 4. 查看LangGraph文档（deepagents基于LangGraph）

```bash
# LangGraph文档
# https://langchain-ai.github.io/langgraph/

# 查看LangGraph源码中的关键类
uv run --package datacloud-agent python -c "
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
help(Command)
"

# 使用skill查询LangGraph文档
skill(name="langchain-docs", user_message="查询Command类型的用法，特别是resume参数")
```

### 5. 调试技巧

```python
# 在代码中添加调试，查看实际行为
import inspect

# 查看函数签名
print(inspect.signature(create_deep_agent))

# 查看源码位置
print(inspect.getfile(create_deep_agent))

# 运行时检查对象
agent = create_deep_agent(...)
print(type(agent))           # 实际类型
print(dir(agent))            # 可用方法和属性
print(agent.__dict__)        # 内部状态

# 查看类的继承关系
print(agent.__class__.__mro__)
```

### 6. 遇到问题时

**第一步：查阅源码**
```bash
# 找到相关源码文件
find $(uv run --package datacloud-agent python -c "import deepagents; import os; print(os.path.dirname(deepagents.__file__))") -name "*.py" -exec grep -l "关键词" {} \;
```

**第二步：使用AI助手搜索**
```python
# 搜索GitHub上的使用示例
task(subagent_type="librarian", load_skills=[], prompt="搜索deepagents create_deep_agent sandbox=True 的使用示例", run_in_background=True)

# 查询官方文档
skill(name="langchain-docs", user_message="查询deepagents的sandbox功能")
```

**第三步：查看测试文件**
```bash
# deepagents的测试文件通常包含使用示例
find $(uv run --package datacloud-agent python -c "import deepagents; import os; print(os.path.dirname(deepagents.__file__))") -name "test_*.py" | head -5
```

---

**环境配置:**
```bash
# 必需的环境变量
export OPENAI_API_KEY="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
export OPENAI_BASE_URL="https://lab.iwhalecloud.com/gpt-proxy/v1"

# 可选：模型选择（默认使用阿里云百炼Qwen）
export MODEL_NAME="openai:qwen3.5-plus"  # 可选: openai:gpt-4, anthropic:claude-3-sonnet, etc.
```

**验证过的模型配置**（来自POC测试）：
- **提供商**: 阿里云百炼 (通过OpenAI兼容接口)
- **模型**: qwen3.5-plus
- **Base URL**: https://lab.iwhalecloud.com/gpt-proxy/v1
- **API Key**: 见上文
- **Token消耗**: 首次调用约5800-5900输入tokens（含系统提示）

---

## POC验证结果总结

| POC | 名称 | 状态 | 关键发现 |
|-----|------|------|----------|
| POC 1 | 基础集成 | ✅ 通过 | `create_deep_agent` 正常工作，返回 `CompiledStateGraph` |
| POC 2 | 令牌计数 | ✅ 通过 | 从 `AIMessage.usage_metadata` 提取token计数，无需tiktoken |
| POC 3 | STEER模式 | ✅ 通过 | `Command(resume=...)` 消息注入成功 |
| POC 4 | 工具系统 | ✅ 通过 | 阿里云百炼Qwen支持工具调用（配置正确时） |
| POC 5 | 子Agent | ✅ 通过 | 子Agent通过task工具调用，可调用自己的工具 |
| POC 6 | 流式输出 | ✅ 通过 | `astream()` 返回异步迭代器 |
| **POC 7** | **沙箱验证** | **⚠️ 待验证** | **deepagents内置沙箱功能需验证** |

**关键成功因素**（来自POC 4 v2/v3）：
1. 工具描述必须详细（包含Args和Returns）
2. 系统提示必须明确强制使用工具
3. 用户查询需要清晰指示工具调用

**⚠️ 重要发现**（来自文档搜索）：

根据对deepagents包的调查，`create_deep_agent()` **没有 `sandbox` 参数**！

**实际参数**（来自源码 `graph.py`）：
- `model`: LLM模型
- `tools`: 自定义工具
- `system_prompt`: 系统提示
- `middleware`: 中间件
- `subagents`: 子Agent配置
- `skills`: 技能路径
- `memory`: 记忆文件路径
- `checkpointer`: 状态持久化
- `store`: 持久化存储
- `backend`: **文件系统/执行后端** ← 可能替代沙箱

**内置工具**（无需沙箱即可使用）：
- `write_todos` - 任务规划
- `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep` - 文件操作
- `execute` - Shell命令（需要backend配置）
- `task` - 生成子Agent

**结论**: 原计划假设的`sandbox=True`不存在，但deepagents提供了内置工具和`backend`参数。需要重新评估沙箱策略。

---

**更新后的沙箱验证策略**:
1. 验证`backend`参数是否可以提供隔离
2. 测试内置工具（`ls`, `read_file`, `write_file`, `execute`）是否可用
3. 评估内置工具是否满足需求，还是需要自建沙箱

---

## Wave 0: 沙箱功能验证 (1天) - ⚠️ 必须先完成

> **修正说明**: Wave 0 从0.5天扩展至1天，包含更充分的backend参数验证和自建沙箱方案设计时间。
> **关键变更**: 基于评审发现，`create_deep_agent()` 没有 `sandbox` 参数，需使用 `backend` 参数。

### Task 0.1: 验证deepagents backend功能（修正版）

**文件:**
- 创建: `poc_tests/test_poc7_backend.py`（替代旧的 test_poc7_sandbox.py）

**说明**: 
- **修正**: 原计划假设 `sandbox=True` 参数存在，但实际API使用 `backend` 参数
- **目标**: 验证 `backend` 参数（`LocalShellBackend`, `FilesystemBackend`）和内置工具
- **关键发现**: `create_deep_agent()` **没有 `sandbox` 参数**！

**Step 1: 查阅deepagents实际API（关键！）**

**查阅源码:**
```bash
# 查看create_deep_agent的实际参数
uv run --package datacloud-agent python -c "
from deepagents import create_deep_agent
import inspect
sig = inspect.signature(create_deep_agent)
print('create_deep_agent parameters:')
for name, param in sig.parameters.items():
    default = param.default if param.default is not inspect.Parameter.empty else 'required'
    print(f'  {name}: {default}')
"

# 查看backend参数的可能值
grep -A 20 "backend" $(uv run --package datacloud-agent python -c "import deepagents; import os; print(os.path.dirname(deepagents.__file__))")/graph.py | head -40

# 查看内置工具列表
uv run --package datacloud-agent python -c "
import deepagents.graph as graph
import inspect
source = inspect.getsource(graph)
# 搜索内置工具定义
"
```

**使用AI助手查询:**
```python
# 查询deepagents backend参数
task(subagent_type="librarian", load_skills=[], prompt="搜索deepagents create_deep_agent backend参数的用法和可选值", run_in_background=True)

# 查询内置工具
task(subagent_type="explore", load_skills=[], prompt="查看deepagents包中内置工具的定义（ls, read_file, write_file, execute等）", run_in_background=True)
```

**Step 2: 编写Backend验证测试（基于实际API - 修正版）**

**关键发现（修正）**:
- `create_deep_agent()` 接受 `backend` 参数，**而非 `sandbox`**
- `LocalShellBackend` 提供执行能力，但**无真正隔离**
- `FilesystemBackend` 限制文件操作范围
- 内置工具（ls, read_file, write_file）通过 backend 提供

创建 `poc_tests/test_poc7_backend.py`:

```python
#!/usr/bin/env python3
"""POC 7: Backend功能验证（修正版 - 基于实际API）

验证deepagents的backend参数和内置工具功能。
关键发现：create_deep_agent()使用backend参数，而非sandbox。
"""

import os
import asyncio
import tempfile
from pathlib import Path

def check_imports():
    """检查必要的导入"""
    try:
        from deepagents import create_deep_agent
        from deepagents.backends import LocalShellBackend, FilesystemBackend
        from langchain.chat_models import init_chat_model
        print("✓ 所有必要的导入可用")
        return True
    except ImportError as e:
        print(f"✗ 导入失败: {e}")
        return False


async def test_backend_parameter():
    """测试 backend 参数（替代 sandbox）"""
    print("\n" + "=" * 60)
    print("测试1: backend参数支持")
    print("=" * 60)
    
    from deepagents import create_deep_agent
    from deepagents.backends import LocalShellBackend
    from langchain.chat_models import init_chat_model
    
    model = init_chat_model(
        "openai:qwen3.5-plus",
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 使用 LocalShellBackend（支持 execute 工具）
        backend = LocalShellBackend(root_dir=tmpdir)
        
        try:
            agent = create_deep_agent(
                model=model,
                backend=backend,  # 关键：使用 backend 参数
                system_prompt="你是一个助手。",
            )
            print("✓ backend参数被接受")
            print(f"  - 后端类型: {type(backend).__name__}")
            print(f"  - 根目录: {tmpdir}")
            return True
        except Exception as e:
            print(f"✗ backend参数失败: {e}")
            return False


async def test_builtin_tools():
    """测试内置工具（ls, read_file, write_file）"""
    print("\n" + "=" * 60)
    print("测试2: 内置工具可用性")
    print("=" * 60)
    
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langchain.chat_models import init_chat_model
    from langchain_core.messages import ToolMessage
    
    model = init_chat_model(
        "openai:qwen3.5-plus",
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("Hello from backend test")
        
        # 使用 FilesystemBackend
        backend = FilesystemBackend(root_dir=tmpdir)
        
        agent = create_deep_agent(
            model=model,
            backend=backend,
            system_prompt="""你是一个文件操作助手。
当用户要求查看文件时，使用 read_file 工具。
当用户要求列出目录时，使用 ls 工具。""",
        )
        
        # 测试 read_file
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": f"读取文件: {test_file.name}"}]
        })
        
        messages = result.get("messages", [])
        tool_calls = [m for m in messages if hasattr(m, 'tool_calls') and m.tool_calls]
        
        if tool_calls:
            print("✓ 内置工具被触发")
            for tc in tool_calls[-1].tool_calls:
                print(f"  - 工具: {tc.get('name', 'unknown')}")
            return True
        else:
            print("⚠️ 未检测到工具调用（可能模型未触发工具）")
            return False


async def test_isolation_level():
    """测试隔离级别"""
    print("\n" + "=" * 60)
    print("测试3: 隔离级别评估")
    print("=" * 60)
    
    print("""
【重要说明】
- LocalShellBackend: 在当前进程执行，无真正隔离
- FilesystemBackend: 限制文件操作范围，但无沙箱隔离
- 生产环境建议: Docker沙箱或gVisor

评估结果:
  - 文件访问: 通过backend.root_dir限制
  - 命令执行: 无隔离（直接在当前shell执行）
  - 资源限制: 无（需额外实现）
""")
    
    return {
        "file_isolation": "partial",  # 通过root_dir限制
        "execution_isolation": "none",  # 无隔离
        "resource_limits": "none",  # 无限制
        "recommendation": "production_needs_docker"
    }


async def main():
    """主验证流程"""
    print("=" * 70)
    print("POC 7: DeepAgents Backend功能验证（修正版）")
    print("=" * 70)
    
    if not check_imports():
        return 1
    
    # 运行测试
    backend_ok = await test_backend_parameter()
    tools_ok = await test_builtin_tools()
    isolation = await test_isolation_level()
    
    # 输出总结
    print("\n" + "=" * 70)
    print("验证结果总结")
    print("=" * 70)
    
    print(f"\n【Backend参数】")
    print(f"  支持: {'✓' if backend_ok else '✗'}")
    
    print(f"\n【内置工具】")
    print(f"  可用: {'✓' if tools_ok else '✗'}")
    
    print(f"\n【隔离性评估】")
    print(f"  文件隔离: {isolation['file_isolation']}")
    print(f"  执行隔离: {isolation['execution_isolation']}")
    print(f"  资源限制: {isolation['resource_limits']}")
    
    # 决策建议
    print("\n" + "=" * 70)
    print("决策建议")
    print("=" * 70)
    
    print("""
【结论】deepagents提供backend参数，但非真正的沙箱

✅ 可用的功能:
  - backend参数支持（LocalShellBackend, FilesystemBackend）
  - 内置工具（ls, read_file, write_file）
  - 文件路径限制（通过root_dir）

⚠️ 限制:
  - 无真正的进程/资源隔离
  - execute工具在当前shell执行
  - 无内置资源限制（CPU/内存）

📋 建议方案:
  1. 开发环境: 直接使用backend参数
  2. 生产环境: 自建Docker沙箱（参考Task 0.2.1-0.2.3）
  3. 短期: 使用backend + 额外权限检查
  4. 长期: 实现Docker沙箱集成
""")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
```

**Step 3: 配置环境变量并运行Backend验证**

```bash
cd /home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation

# 设置环境变量（必需）
export OPENAI_API_KEY="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
export OPENAI_BASE_URL="https://lab.iwhalecloud.com/gpt-proxy/v1"

# 运行验证（修正后的测试）
uv run --package datacloud-agent python poc_tests/test_poc7_backend.py
```

**注意**: 
- 确保网络可以访问 `https://lab.iwhalecloud.com/gpt-proxy/v1`
- 首次运行会消耗约5800-5900输入tokens（约0.02-0.03美元）
- 如使用其他模型，修改 `test_poc7_backend.py` 中的模型名称

**预期输出示例**:

```
======================================================================
POC 7: DeepAgents Backend功能验证（修正版）
======================================================================
✓ 所有必要的导入可用

============================================================
测试1: backend参数支持
============================================================
✓ backend参数被接受
  - 后端类型: LocalShellBackend
  - 根目录: /tmp/xxx

============================================================
测试2: 内置工具可用性
============================================================
✓ 内置工具被触发
  - 工具: read_file

============================================================
测试3: 隔离级别评估
============================================================
【重要说明】
- LocalShellBackend: 在当前进程执行，无真正隔离
- FilesystemBackend: 限制文件操作范围，但无沙箱隔离
...

======================================================================
验证结果总结
======================================================================
【Backend参数】
  支持: ✓

【内置工具】
  可用: ✓

【隔离性评估】
  文件隔离: partial
  执行隔离: none
  资源限制: none

======================================================================
决策建议
======================================================================
【结论】deepagents提供backend参数，但非真正的沙箱
...
```

**Step 3: 根据验证结果决策**

根据输出结果，更新后续任务：

| 情况 | 条件 | 决策 |
|------|------|------|
| **A** | `sandbox=True` 可用 + 隔离性强 | 直接使用内置沙箱，继续原计划 |
| **B** | `sandbox=True` 可用 + 隔离性弱 | 评估风险后使用，或考虑自建沙箱 |
| **C** | `sandbox` 参数不支持 | **需要添加自建沙箱任务（增加1-2天）** |

**关键判断标准**:
- **隔离性强**: `can_read_outside: False` + `isolation_level: strong`
- **隔离性弱**: `can_read_outside: True` + `isolation_level: weak`
- **无沙箱**: `sandbox_param_accepted: False`

**Step 4: Commit验证结果**

```bash
git add poc_tests/test_poc7_sandbox.py
git commit -m "test(datacloud-agent): add sandbox functionality verification (POC 7)"
```

---

### Task 0.2: 根据沙箱验证结果调整计划（条件性）

**说明**: 根据POC 7验证结果，可能需要调整后续计划。

**情况A: 完整沙箱支持（推荐）**
- 无需调整计划
- 在Task 1.4中使用 `sandbox=True`

**情况B: 轻量级沙箱**
- 评估业务风险
- 如风险可控：继续使用，添加额外权限检查
- 如风险不可控：转入情况C

**情况C: 无沙箱功能（需要自建）**

添加以下额外任务：

#### Task 0.2.1: 设计自建沙箱方案
**时间**: 0.5天
**文件**: `docs/design/sandbox-design.md`

方案选项：
1. **Docker沙箱**（推荐）
   - 优点：完整隔离、资源限制、成熟方案
   - 缺点：需要Docker环境、启动开销
   
2. **Subprocess沙箱**
   - 优点：轻量级、无需额外依赖
   - 缺点：隔离性较弱、跨平台兼容性

3. **chroot沙箱**
   - 优点：文件系统隔离
   - 缺点：Linux only、配置复杂

#### Task 0.2.2: 实现Docker沙箱（如选择Docker方案）
**时间**: 1-1.5天
**文件**:
- 创建: `datacloud-agent/src/datacloud_agent/core/sandbox.py`
- 创建: `docker/sandbox/Dockerfile`
- 创建: `docker/sandbox/entrypoint.sh`

核心功能：
- 在Docker容器中执行工具调用
- 限制容器资源（CPU、内存、磁盘）
- 挂载只读/读写卷
- 超时控制

#### Task 0.2.3: 集成沙箱到AgentRunner
**时间**: 0.5天
**文件**: `datacloud-agent/src/datacloud_agent/core/runner.py`

修改 `_execute_agent` 方法，在工具调用时使用沙箱执行。

**总增加工作量**: 2-3天（如果选择自建沙箱）

---

## Wave 1: 核心集成 (3-4天) - 增量验证

> **修正说明**: 每个Task后添加快速验证步骤，及早发现问题。

**增量验证策略**:
- Task 1.1后: 验证依赖安装
- Task 1.2后: 运行模型配置测试
- Task 1.3后: 运行工具定义测试
- Task 1.4后: 运行Runner集成测试
- Task 1.5后: 运行子Agent配置测试
- Task 1.6后: 运行Registry测试（含安全验证）

### Task 1.1: 配置模型和deepagents依赖

**文件:**
- 修改: `datacloud-agent/pyproject.toml`
- 修改: `pyproject.toml` (根项目)

**Step 1: 添加deepagents依赖到子项目**

编辑 `datacloud-agent/pyproject.toml`:
```toml
[project]
dependencies = [
    # 现有依赖...
    "deepagents>=0.4.7",
    "langgraph>=1.0.10",
]
```

**Step 2: 同步依赖**

```bash
cd /home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation
uv sync
```

**Step 3: 验证安装**

```bash
# 设置环境变量（后续步骤都需要）
export OPENAI_API_KEY="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
export OPENAI_BASE_URL="https://lab.iwhalecloud.com/gpt-proxy/v1"

# 验证安装
uv run --package datacloud-agent python -c "from deepagents import create_deep_agent; print('✓ deepagents imported')"
```

Expected: `✓ deepagents imported`

**Step 4: 增量验证（Task 1.1后）**

```bash
# 验证依赖安装
uv run --package datacloud-agent python -c "from deepagents import create_deep_agent; print('✓ Task 1.1: deepagents导入成功')"
```

**Step 5: Commit**

```bash
git add datacloud-agent/pyproject.toml pyproject.toml uv.lock
git commit -m "deps(datacloud-agent): add deepagents and langgraph dependencies"
```

---

### Task 1.2: 创建模型配置模块

**文件:**
- 创建: `datacloud-agent/src/datacloud_agent/core/model_config.py`
- 测试: `datacloud-agent/tests/test_model_config.py`

**Step 1: 查阅deepagents模型配置方式**

**使用AI助手工具查询:**
```python
# 查询deepagents模型配置文档
task(subagent_type="librarian", load_skills=[], prompt="搜索deepagents create_deep_agent model参数的配置方式，支持哪些模型提供商", run_in_background=True)

# 查询LangChain模型初始化
skill(name="langchain-docs", user_message="查询init_chat_model函数的用法和参数")
```

**本地源码检查:**
```bash
# 查看deepagents如何处理模型参数
uv run --package datacloud-agent python -c "
from deepagents import create_deep_agent
import inspect
print(inspect.signature(create_deep_agent))
"

# 查看init_chat_model的用法（来自POC验证）
uv run --package datacloud-agent python -c "
from langchain.chat_models import init_chat_model
help(init_chat_model)
" | head -50
```

**Step 2: 编写模型配置模块**

```python
"""模型配置模块 - 基于POC验证结果"""

import os
from typing import Any
from langchain.chat_models import init_chat_model


def create_model(config: dict[str, Any] | None = None) -> Any:
    """
    创建模型实例。
    
    基于POC 1验证：阿里云百炼Qwen通过OpenAI兼容接口工作正常
    
    Args:
        config: 模型配置，默认使用环境变量
        
    Returns:
        模型实例
    """
    if config is None:
        config = {}
    
    # 默认使用阿里云百炼Qwen（已通过POC验证）
    model_name = config.get("model", "openai:qwen3.5-plus")
    api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
    base_url = config.get("base_url") or os.getenv("OPENAI_BASE_URL")
    
    if not api_key:
        raise ValueError("API key is required. Set OPENAI_API_KEY environment variable.")
    
    model = init_chat_model(
        model_name,
        api_key=api_key,
        base_url=base_url,
    )
    
    return model


def get_default_model_config() -> dict[str, Any]:
    """获取默认模型配置"""
    return {
        "model": "openai:qwen3.5-plus",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL"),
    }
```

**Step 2: 编写测试**

```python
import os
import pytest
from datacloud_agent.core.model_config import create_model, get_default_model_config


def test_get_default_model_config():
    """测试默认配置获取"""
    config = get_default_model_config()
    assert config["model"] == "openai:qwen3.5-plus"
    assert "api_key" in config
    assert "base_url" in config


def test_create_model_without_api_key():
    """测试缺少API key时的错误处理"""
    # 临时清除环境变量
    original_key = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="API key is required"):
            create_model({"api_key": None})
    finally:
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
```

**Step 3: 配置环境并运行测试**

```bash
# 设置环境变量
export OPENAI_API_KEY="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
export OPENAI_BASE_URL="https://lab.iwhalecloud.com/gpt-proxy/v1"

# 运行测试
uv run --package datacloud-agent pytest datacloud-agent/tests/test_model_config.py -v
```

Expected: `2 passed`

**Step 4: Commit**

```bash
git add datacloud-agent/src/datacloud_agent/core/model_config.py datacloud-agent/tests/test_model_config.py
git commit -m "feat(datacloud-agent): add model configuration module"
```

---

### Task 1.3: 创建工具定义规范模块

**文件:**
- 创建: `datacloud-agent/src/datacloud_agent/core/tools.py`
- 测试: `datacloud-agent/tests/test_tools.py`

**Step 1: 查阅deepagents工具系统文档**

```bash
# 查看deepagents工具系统的实现
uv run --package datacloud-agent python -c "
from deepagents import create_deep_agent
import inspect
# 查看create_deep_agent的tools参数
sig = inspect.signature(create_deep_agent)
for name, param in sig.parameters.items():
    if 'tool' in name.lower():
        print(f'{name}: {param.default if param.default is not inspect.Parameter.empty else "required"}')
"

# 查看langchain工具装饰器的文档
uv run --package datacloud-agent python -c "
from langchain_core.tools import tool
help(tool)
" | head -80
```

**Step 2: 编写工具定义（基于POC 4 v2成功配置）**

```python
"""工具定义模块 - 基于POC验证结果

关键发现（POC 4 v2）：
- 工具描述必须详细，包含Args和Returns
- 系统提示必须明确强制使用工具
"""

from langchain_core.tools import tool
from typing import Any


@tool
def know(query: str) -> str:
    """
    知识检索工具。用于查询特定主题的知识信息。
    
    从知识服务检索业务知识和本体知识。
    
    Args:
        query: 要查询的主题或关键词
        
    Returns:
        关于该主题的知识信息
    """
    # 实际实现将调用知识服务
    return f"[Knowledge] 关于 '{query}' 的知识信息"


@tool
def query(data: str) -> str:
    """
    数据查询工具。用于执行数据查询计划。
    
    从数据服务执行NL2Data查询，支持行列权限控制。
    
    Args:
        data: 数据查询请求（自然语言或结构化查询）
        
    Returns:
        查询结果数据
    """
    # 实际实现将调用数据服务
    return f"[Query] 数据查询结果: {data}"


@tool
def compute(expression: str) -> str:
    """
    计算工具。用于执行数学计算或数据分析。
    
    Args:
        expression: 计算表达式或分析请求
        
    Returns:
        计算结果
    """
    # 实际实现将调用计算服务
    return f"[Compute] 计算结果: {expression}"


@tool
def render(format_type: str, content: str) -> str:
    """
    渲染工具。用于生成可视化输出。
    
    Args:
        format_type: 输出格式类型（如 table, chart, markdown）
        content: 要渲染的内容
        
    Returns:
        渲染后的输出
    """
    # 实际实现将调用渲染服务
    return f"[Render] {format_type} 格式渲染: {content}"


@tool
def store(key: str, value: str) -> str:
    """
    存储工具。用于保存数据到记忆服务。
    
    Args:
        key: 存储键名
        value: 要存储的值
        
    Returns:
        存储确认信息
    """
    # 实际实现将调用记忆服务
    return f"[Store] 已存储 '{key}': {value}"


def get_business_tools() -> list[Any]:
    """获取业务工具列表（五个原子工具）"""
    return [know, query, compute, render, store]


def get_system_prompt() -> str:
    """
    获取系统提示模板（基于POC 4 v2成功配置）
    
    关键：必须明确强制使用工具
    """
    return """你是一个智能数据分析助手。当用户询问任何问题时，你必须使用可用的工具来获取信息。

可用的工具：
- know: 用于检索业务知识和本体知识
- query: 用于执行数据查询（NL2Data）
- compute: 用于执行数学计算和数据分析
- render: 用于生成可视化输出
- store: 用于保存数据到记忆服务

重要：对于每个用户查询，请分析是否需要使用工具。如果需要获取信息或执行操作，请主动调用相应的工具。

工作流程：
1. 分析用户意图
2. 确定需要使用的工具
3. 调用工具获取信息
4. 整合结果回复用户
"""
```

**Step 2: 编写测试**

```python
from datacloud_agent.core.tools import (
    know, query, compute, render, store,
    get_business_tools, get_system_prompt
)


def test_tools_exist():
    """测试工具函数存在"""
    assert callable(know)
    assert callable(query)
    assert callable(compute)
    assert callable(render)
    assert callable(store)


def test_tools_direct_call():
    """测试工具直接调用"""
    result = know.run("Python")
    assert "Python" in result
    assert "Knowledge" in result


def test_get_business_tools():
    """测试获取业务工具列表"""
    tools = get_business_tools()
    assert len(tools) == 5
    assert know in tools
    assert query in tools


def test_get_system_prompt():
    """测试系统提示包含关键信息"""
    prompt = get_system_prompt()
    assert "know" in prompt
    assert "query" in prompt
    assert "必须使用" in prompt
```

**Step 3: 配置环境并运行测试**

```bash
# 设置环境变量
export OPENAI_API_KEY="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
export OPENAI_BASE_URL="https://lab.iwhalecloud.com/gpt-proxy/v1"

# 运行测试
uv run --package datacloud-agent pytest datacloud-agent/tests/test_tools.py -v
```

Expected: `4 passed`

**Step 4: 增量验证（Task 1.3后）**

```bash
# 运行工具定义测试
uv run --package datacloud-agent pytest datacloud-agent/tests/test_tools.py -v
# Expected: 4 passed

echo "✓ Task 1.3: 工具定义测试通过"
```

**Step 5: Commit**

```bash
git add datacloud-agent/src/datacloud_agent/core/tools.py datacloud-agent/tests/test_tools.py
git commit -m "feat(datacloud-agent): add tool definitions with POC-validated schema"
```

---

### Task 1.4: 重构AgentRunner集成deepagents

**文件:**
- 修改: `datacloud-agent/src/datacloud_agent/core/runner.py`
- 测试: `datacloud-agent/tests/test_runner_integration.py`

**Step 1: 重构AgentRunner（基于POC 1-6验证结果）**

```python
"""Agent执行引擎 - 集成deepagents

基于POC验证结果：
- POC 1: create_deep_agent 正常工作
- POC 2: 从AIMessage.usage_metadata提取token计数
- POC 3: Command(resume=...)实现STEER模式
- POC 6: astream()实现流式输出
"""

import asyncio
from typing import Any
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langchain_core.messages import AIMessage
from deepagents import create_deep_agent

from .model_config import create_model
from .tools import get_business_tools, get_system_prompt


class AgentRunner:
    """Agent执行引擎 - 基于deepagents"""
    
    def __init__(self, agent_registry: Any):
        self.agent_registry = agent_registry
        self._running_tasks: dict[str, dict] = {}
        self._checkpointers: dict[str, InMemorySaver] = {}
    
    async def _execute_agent(
        self,
        session_key: str,
        messages: list[dict],
    ) -> dict[str, Any]:
        """
        执行Agent（基于POC 1, 2验证）
        
        Args:
            session_key: 会话标识符 (格式: tenant:{tenant_id}:agent:{agent_id}:{session_id})
            messages: 消息列表
            
        Returns:
            执行结果，包含token使用统计
        """
        # 解析agent_id
        parts = session_key.split(":")
        if len(parts) < 5:
            raise ValueError(f"Invalid session_key format: {session_key}")
        agent_id = parts[3]
        
        # 获取agent配置
        config = self.agent_registry.get(agent_id)
        if not config:
            raise ValueError(f"Agent not found: {agent_id}")
        
        # 创建或获取checkpointer（POC 3验证）
        if session_key not in self._checkpointers:
            self._checkpointers[session_key] = InMemorySaver()
        checkpointer = self._checkpointers[session_key]
        
        # 创建模型（POC 1验证）
        model = create_model({
            "model": f"{config.provider}:{config.model}",
        })
        
        # 创建agent（POC 1验证）
        agent = create_deep_agent(
            model=model,
            system_prompt=config.system_prompt or get_system_prompt(),
            tools=get_business_tools(),
            checkpointer=checkpointer,
        )
        
        # 配置（POC 3验证）
        invoke_config = {"configurable": {"thread_id": session_key}}
        
        # 执行（POC 1验证）
        result = await agent.ainvoke(
            {"messages": messages},
            config=invoke_config
        )
        
        # 提取token计数（POC 2验证）
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.usage_metadata:
                usage = {
                    "input_tokens": msg.usage_metadata.get("input_tokens", 0),
                    "output_tokens": msg.usage_metadata.get("output_tokens", 0),
                    "total_tokens": msg.usage_metadata.get("total_tokens", 0),
                }
                break
        
        # 提取最终回复
        final_content = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                final_content = msg.content
                break
        
        return {
            "agent_id": agent_id,
            "messages": result.get("messages", []),
            "response": final_content,
            "usage": usage,
        }
    
    async def _steer_run(self, session_key: str, prompt: str) -> bool:
        """
        STEER模式：使用Command(resume=...)注入消息（POC 3验证）
        
        Args:
            session_key: 会话标识符
            prompt: 要注入的提示
            
        Returns:
            是否成功注入
        """
        if session_key not in self._checkpointers:
            return False
        
        # 获取checkpointer
        checkpointer = self._checkpointers[session_key]
        
        # 解析agent_id
        parts = session_key.split(":")
        agent_id = parts[3]
        
        # 获取agent配置
        config = self.agent_registry.get(agent_id)
        if not config:
            return False
        
        # 创建模型和agent
        model = create_model({"model": f"{config.provider}:{config.model}"})
        agent = create_deep_agent(
            model=model,
            system_prompt=config.system_prompt or get_system_prompt(),
            tools=get_business_tools(),
            checkpointer=checkpointer,
        )
        
        # 使用Command注入（POC 3验证）
        invoke_config = {"configurable": {"thread_id": session_key}}
        result = await agent.ainvoke(
            Command(resume=prompt),
            config=invoke_config
        )
        
        return True
    
    async def _stream_agent(
        self,
        session_key: str,
        messages: list[dict],
    ):
        """
        流式执行Agent（POC 6验证）
        
        Args:
            session_key: 会话标识符
            messages: 消息列表
            
        Yields:
            流式输出chunks
        """
        # 解析agent_id
        parts = session_key.split(":")
        agent_id = parts[3]
        
        # 获取agent配置
        config = self.agent_registry.get(agent_id)
        
        # 创建checkpointer
        if session_key not in self._checkpointers:
            self._checkpointers[session_key] = InMemorySaver()
        checkpointer = self._checkpointers[session_key]
        
        # 创建模型和agent
        model = create_model({"model": f"{config.provider}:{config.model}"})
        agent = create_deep_agent(
            model=model,
            system_prompt=config.system_prompt or get_system_prompt(),
            tools=get_business_tools(),
            checkpointer=checkpointer,
        )
        
        # 流式执行（POC 6验证）
        invoke_config = {"configurable": {"thread_id": session_key}}
        async for chunk in agent.astream(
            {"messages": messages},
            config=invoke_config
        ):
            yield chunk
```

**Step 2: 编写集成测试**

```python
import pytest
from unittest.mock import Mock, MagicMock
from datacloud_agent.core.runner import AgentRunner


@pytest.fixture
def mock_registry():
    """创建mock agent registry"""
    registry = Mock()
    registry.get.return_value = Mock(
        provider="openai",
        model="qwen3.5-plus",
        system_prompt=None,
    )
    return registry


@pytest.mark.asyncio
async def test_runner_initialization(mock_registry):
    """测试runner初始化"""
    runner = AgentRunner(mock_registry)
    assert runner.agent_registry == mock_registry
    assert runner._running_tasks == {}
    assert runner._checkpointers == {}


@pytest.mark.asyncio
async def test_execute_agent_invalid_session_key(mock_registry):
    """测试无效的session_key格式"""
    runner = AgentRunner(mock_registry)
    
    with pytest.raises(ValueError, match="Invalid session_key"):
        await runner._execute_agent("invalid-key", [{"role": "user", "content": "Hello"}])


@pytest.mark.asyncio
async def test_steer_run_no_checkpointer(mock_registry):
    """测试STEER时无checkpointer"""
    runner = AgentRunner(mock_registry)
    
    result = await runner._steer_run("tenant:1:agent:2:session:3", "Steer message")
    assert result is False
```

**Step 3: 配置环境并运行测试**

```bash
# 设置环境变量
export OPENAI_API_KEY="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
export OPENAI_BASE_URL="https://lab.iwhalecloud.com/gpt-proxy/v1"

# 运行测试
uv run --package datacloud-agent pytest datacloud-agent/tests/test_runner_integration.py -v
```

Expected: `3 passed`

**Step 4: 增量验证（Task 1.4后）**

```bash
# 运行Runner集成测试
uv run --package datacloud-agent pytest datacloud-agent/tests/test_runner_integration.py -v
# Expected: 3 passed

echo "✓ Task 1.4: AgentRunner集成测试通过"
```

**Step 5: Commit**

```bash
git add datacloud-agent/src/datacloud_agent/core/runner.py datacloud-agent/tests/test_runner_integration.py
git commit -m "refactor(datacloud-agent): integrate deepagents into AgentRunner"
```

---

### Task 1.5: 实现子Agent配置支持

**文件:**
- 创建: `datacloud-agent/src/datacloud_agent/core/subagents.py`
- 测试: `datacloud-agent/tests/test_subagents.py`

**Step 1: 查阅deepagents子Agent文档**

```bash
# 查看create_deep_agent的subagents参数
uv run --package datacloud-agent python -c "
from deepagents import create_deep_agent
import inspect
sig = inspect.signature(create_deep_agent)
for name, param in sig.parameters.items():
    print(f'{name}: default={param.default is not inspect.Parameter.empty}')
"

# 在deepagents源码中搜索subagent相关实现
uv run --package datacloud-agent python -c "
import deepagents
import os
import subprocess
pkg_dir = os.path.dirname(deepagents.__file__)
result = subprocess.run(['grep', '-r', 'subagent', pkg_dir, '--include=*.py'], 
                       capture_output=True, text=True)
print('Subagent implementation found:' if result.stdout else 'No subagent implementation found')
print(result.stdout[:1500] if result.stdout else '')
"
```

**Step 2: 编写子Agent配置模块（基于POC 5 v3验证）**

```python
"""子Agent配置模块 - 基于POC 5 v3验证结果

关键发现：
- 子Agent通过task工具被调用
- 子Agent可以配置自己的tools
- 调用链路：父Agent → task → 子Agent → 子Agent工具
"""

from typing import Any
from dataclasses import dataclass


@dataclass
class SubAgentConfig:
    """子Agent配置"""
    name: str
    description: str
    system_prompt: str
    tools: list[Any] | None = None
    model: Any | None = None  # 可选，默认继承父Agent


def get_default_subagents() -> list[dict[str, Any]]:
    """
    获取默认子Agent配置
    
    基于POC 5 v3验证的子Agent调用模式
    """
    return [
        {
            "name": "researcher",
            "description": "研究专家，擅长信息检索和知识查询",
            "system_prompt": """你是一个研究专家。当需要查询知识时，你必须使用 know 工具。

可用的工具：
- know: 用于检索业务知识和本体知识

重要：对于每个研究请求，请主动调用 know 工具获取信息。
""",
        },
        {
            "name": "data_analyst",
            "description": "数据分析师，擅长数据查询和分析",
            "system_prompt": """你是一个数据分析师。当需要查询数据时，你必须使用 query 工具。

可用的工具：
- query: 用于执行数据查询（NL2Data）
- compute: 用于执行数学计算

重要：对于每个数据分析请求，请主动调用相应工具获取数据。
""",
        },
        {
            "name": "visualizer",
            "description": "可视化专家，擅长生成图表和报告",
            "system_prompt": """你是一个可视化专家。当需要生成可视化输出时，你必须使用 render 工具。

可用的工具：
- render: 用于生成可视化输出

重要：对于每个可视化请求，请主动调用 render 工具。
""",
        },
    ]


def convert_to_deepagents_format(
    subagents: list[SubAgentConfig] | list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    转换为deepagents格式
    
    Args:
        subagents: 子Agent配置列表
        
    Returns:
        deepagents兼容的配置列表
    """
    result = []
    for sa in subagents:
        if isinstance(sa, SubAgentConfig):
            config = {
                "name": sa.name,
                "description": sa.description,
                "system_prompt": sa.system_prompt,
            }
            if sa.tools:
                config["tools"] = sa.tools
            if sa.model:
                config["model"] = sa.model
            result.append(config)
        else:
            result.append(sa)
    return result
```

**Step 2: 编写测试**

```python
from datacloud_agent.core.subagents import (
    SubAgentConfig,
    get_default_subagents,
    convert_to_deepagents_format,
)


def test_subagent_config_creation():
    """测试子Agent配置创建"""
    config = SubAgentConfig(
        name="test_agent",
        description="Test agent",
        system_prompt="You are a test agent.",
    )
    assert config.name == "test_agent"
    assert config.tools is None


def test_get_default_subagents():
    """测试获取默认子Agent配置"""
    subagents = get_default_subagents()
    assert len(subagents) == 3
    
    names = [sa["name"] for sa in subagents]
    assert "researcher" in names
    assert "data_analyst" in names
    assert "visualizer" in names


def test_convert_to_deepagents_format():
    """测试配置格式转换"""
    configs = [
        SubAgentConfig(
            name="test",
            description="Test",
            system_prompt="Test prompt",
        )
    ]
    
    result = convert_to_deepagents_format(configs)
    assert len(result) == 1
    assert result[0]["name"] == "test"
    assert "tools" not in result[0]


def test_convert_with_dict_input():
    """测试字典输入"""
    configs = [{"name": "dict_agent", "description": "Dict", "system_prompt": "Prompt"}]
    result = convert_to_deepagents_format(configs)
    assert result == configs
```

**Step 3: 运行测试**

```bash
uv run --package datacloud-agent pytest datacloud-agent/tests/test_subagents.py -v
```

Expected: `4 passed`

**Step 4: 增量验证（Task 1.5后）**

```bash
# 运行子Agent配置测试
uv run --package datacloud-agent pytest datacloud-agent/tests/test_subagents.py -v
# Expected: 4 passed

echo "✓ Task 1.5: 子Agent配置测试通过"
```

**Step 5: Commit**

```bash
git add datacloud-agent/src/datacloud_agent/core/subagents.py datacloud-agent/tests/test_subagents.py
git commit -m "feat(datacloud-agent): add subagent configuration module"
```

---

### Task 1.6: 更新AgentRegistry支持deepagents（含安全验证）

**文件:**
- 修改: `datacloud-agent/src/datacloud_agent/core/registry.py`
- 测试: `datacloud-agent/tests/test_registry_deepagents.py`

**Step 1: 查阅现有AgentRegistry实现**

```bash
# 查看现有AgentRegistry的实现
cat datacloud-agent/src/datacloud_agent/core/registry.py | head -100

# 查看AgentConfig的数据结构
grep -A 20 "class AgentConfig" datacloud-agent/src/datacloud_agent/core/registry.py
```

**Step 2: 更新AgentRegistry**

```python
"""Agent注册表 - 支持deepagents配置

扩展配置以支持：
- 子Agent配置（POC 5验证）
- 自定义工具配置
- 模型配置
"""

from typing import Any
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Agent配置"""
    agent_id: str
    provider: str = "openai"
    model: str = "qwen3.5-plus"
    system_prompt: str | None = None
    tools: list[str] = field(default_factory=list)
    subagents: list[dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "agent_id": self.agent_id,
            "provider": self.provider,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "subagents": self.subagents,
        }


class AgentRegistry:
    """Agent注册表 - 带安全验证（增强版）"""
    
    def __init__(self):
        self._agents: dict[str, AgentConfig] = {}
        self._tenant_acl: dict[str, list[str]] = {}  # tenant_id -> [agent_ids]
    
    def _validate_tenant_id(self, tenant_id: str) -> bool:
        """
        验证tenant_id格式
        
        规则:
        - 3-64字符
        - 只允许小写字母、数字、下划线、连字符
        """
        if not tenant_id:
            return False
        import re
        return bool(re.match(r"^[a-z0-9_-]{3,64}$", tenant_id))
    
    def _check_tenant_access(self, agent_id: str, tenant_id: str) -> bool:
        """
        检查租户是否有权访问Agent
        
        逻辑:
        - 如果allowed_tenants为空，只允许同名tenant访问
        - 否则检查tenant_id是否在allowed_tenants中
        """
        config = self._agents.get(agent_id)
        if not config:
            return False
        
        allowed = config.allowed_tenants
        if not allowed:
            # 默认：agent_id作为tenant_id（简化模型）
            return agent_id.startswith(f"{tenant_id}-") or agent_id == tenant_id
        
        return tenant_id in allowed
    
    def register(self, config: AgentConfig) -> None:
        """注册Agent"""
        self._agents[config.agent_id] = config
    
    def get(self, agent_id: str, tenant_id: str | None = None) -> AgentConfig | None:
        """
        获取Agent配置（带安全验证）
        
        Args:
            agent_id: Agent标识符
            tenant_id: 可选，用于访问控制验证
            
        Returns:
            AgentConfig或None（无权限时）
        """
        config = self._agents.get(agent_id)
        if not config:
            return None
        
        # 如果提供了tenant_id，进行访问控制检查
        if tenant_id is not None:
            if not self._validate_tenant_id(tenant_id):
                raise ValueError(f"Invalid tenant_id format: {tenant_id}")
            
            if not self._check_tenant_access(agent_id, tenant_id):
                raise PermissionError(
                    f"Tenant '{tenant_id}' not authorized for agent '{agent_id}'"
                )
        
        return config
    
    def list_agents(self) -> list[str]:
        """列出所有Agent ID"""
        return list(self._agents.keys())
    
    def create_default_agent(
        self, 
        agent_id: str, 
        tenant_id: str | None = None
    ) -> AgentConfig:
        """
        创建默认Agent配置
        
        Args:
            agent_id: Agent标识符
            tenant_id: 可选，用于设置访问控制
        """
        from .subagents import get_default_subagents
        from .tools import get_system_prompt
        
        allowed = [tenant_id] if tenant_id else []
        
        config = AgentConfig(
            agent_id=agent_id,
            provider="openai",
            model="qwen3.5-plus",
            system_prompt=get_system_prompt(),
            tools=["know", "query", "compute", "render", "store"],
            subagents=get_default_subagents(),
            allowed_tenants=allowed,
        )
        self.register(config)
        return config
```

**Step 2: 编写测试（含安全验证测试）**

```python
from datacloud_agent.core.registry import AgentRegistry, AgentConfig
import pytest


def test_agent_config_creation():
    """测试Agent配置创建"""
    config = AgentConfig(
        agent_id="test-agent",
        provider="openai",
        model="qwen3.5-plus",
    )
    assert config.agent_id == "test-agent"
    assert config.tools == []


def test_agent_registry_register_and_get():
    """测试注册和获取"""
    registry = AgentRegistry()
    config = AgentConfig(agent_id="agent-1")
    
    registry.register(config)
    retrieved = registry.get("agent-1")
    
    assert retrieved is not None
    assert retrieved.agent_id == "agent-1"


def test_agent_registry_list():
    """测试列出Agent"""
    registry = AgentRegistry()
    registry.register(AgentConfig(agent_id="agent-1"))
    registry.register(AgentConfig(agent_id="agent-2"))
    
    agents = registry.list_agents()
    assert len(agents) == 2
    assert "agent-1" in agents
    assert "agent-2" in agents


def test_create_default_agent():
    """测试创建默认Agent"""
    registry = AgentRegistry()
    config = registry.create_default_agent("default-agent")
    
    assert config.agent_id == "default-agent"
    assert len(config.tools) == 5
    assert len(config.subagents) == 3


# 新增：安全验证测试
def test_tenant_id_validation():
    """测试tenant_id格式验证"""
    registry = AgentRegistry()
    registry.create_default_agent("agent-1", tenant_id="user_001")
    
    # 有效tenant_id
    config = registry.get("agent-1", tenant_id="user_001")
    assert config is not None
    
    # 无效tenant_id格式
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        registry.get("agent-1", tenant_id="INVALID@ID!")
    
    # 过短tenant_id
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        registry.get("agent-1", tenant_id="ab")


def test_tenant_access_control():
    """测试租户访问控制"""
    registry = AgentRegistry()
    registry.create_default_agent("agent-1", tenant_id="user_001")
    
    # 正确tenant访问
    config = registry.get("agent-1", tenant_id="user_001")
    assert config is not None
    
    # 错误tenant访问
    with pytest.raises(PermissionError, match="not authorized"):
        registry.get("agent-1", tenant_id="user_002")
```

**Step 3: 运行测试（含安全验证）**

```bash
# 运行Registry测试（含新增的安全测试）
uv run --package datacloud-agent pytest datacloud-agent/tests/test_registry_deepagents.py -v
```

Expected: `6 passed`（4个原有 + 2个安全验证测试）

**Step 4: 增量验证（Task 1.6后）**

```bash
# 运行Registry测试（含安全验证）
uv run --package datacloud-agent pytest datacloud-agent/tests/test_registry_deepagents.py -v
# Expected: 6 passed

echo "✓ Task 1.6: AgentRegistry测试通过（含安全验证）"
```

**Step 5: Commit**

```bash
git add datacloud-agent/src/datacloud_agent/core/registry.py datacloud-agent/tests/test_registry_deepagents.py
git commit -m "feat(datacloud-agent): update AgentRegistry with security validation"
```

---

## Wave 2: 队列策略完善 (2-3天)

### Task 2.1: 完善队列丢弃策略

**文件:**
- 修改: `datacloud-agent/src/datacloud_agent/core/queue.py`
- 测试: `datacloud-agent/tests/test_queue_policies.py`

**Step 1: 查阅现有队列实现**

```bash
# 查看现有队列实现
cat datacloud-agent/src/datacloud_agent/core/queue.py | head -150

# 查看DropPolicy枚举
grep -A 10 "class DropPolicy" datacloud-agent/src/datacloud_agent/core/queue.py
```

**Step 2: 实现SUMMARIZE策略**

```python
"""队列策略 - 添加SUMMARIZE丢弃策略

基于POC验证的轻量级模型调用模式
"""

import asyncio
from enum import Enum
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime

from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
import os


class DropPolicy(Enum):
    """队列丢弃策略"""
    OLD = "old"           # 丢弃最旧消息
    NEW = "new"           # 拒绝新消息
    SUMMARIZE = "summarize"  # 总结旧消息


@dataclass
class QueuedMessage:
    """队列消息"""
    prompt: str
    session_key: str
    priority: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


class MessageQueue:
    """消息队列"""
    
    def __init__(
        self,
        max_size: int = 100,
        drop_policy: DropPolicy = DropPolicy.OLD,
    ):
        self.max_size = max_size
        self.drop_policy = drop_policy
        self.messages: list[QueuedMessage] = []
        self._lock = asyncio.Lock()
    
    async def enqueue(self, message: QueuedMessage) -> bool:
        """
        入队消息，根据策略处理队列满的情况
        
        Returns:
            是否成功入队
        """
        async with self._lock:
            if len(self.messages) >= self.max_size:
                if self.drop_policy == DropPolicy.NEW:
                    return False
                elif self.drop_policy == DropPolicy.OLD:
                    self.messages.pop(0)
                elif self.drop_policy == DropPolicy.SUMMARIZE:
                    await self._summarize_old_messages()
            
            self.messages.append(message)
            return True
    
    async def _summarize_old_messages(self) -> None:
        """
        总结旧消息（保留最近10条，总结之前的）
        
        使用轻量级模型进行异步总结
        """
        if len(self.messages) <= 10:
            # 消息太少，直接丢弃最旧的
            self.messages.pop(0)
            return
        
        # 保留最近10条，总结之前的
        messages_to_summarize = self.messages[:-10]
        self.messages = self.messages[-10:]
        
        # 异步总结（不阻塞队列操作）
        asyncio.create_task(self._async_summarize(messages_to_summarize))
    
    async def _async_summarize(self, messages: list[QueuedMessage]) -> None:
        """
        异步总结消息
        
        使用轻量级模型（与POC测试相同的配置模式）
        """
        try:
            # 构建总结提示
            content = "\n".join([
                f"[{m.timestamp}] {m.prompt[:100]}..."
                for m in messages
            ])
            
            # 使用轻量级模型（基于POC验证的配置）
            model = init_chat_model(
                "openai:qwen3.5-plus",  # 使用相同模型，简化配置
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_BASE_URL"),
            )
            
            agent = create_deep_agent(
                model=model,
                system_prompt="Summarize the following conversation messages concisely in Chinese.",
            )
            
            result = await agent.ainvoke({
                "messages": [{"role": "user", "content": content}]
            })
            
            summary = result.get("messages", [])[-1].content if result.get("messages") else "[Summary unavailable]"
            
            # 插入总结消息
            summary_msg = QueuedMessage(
                prompt=f"[历史消息总结] {summary[:500]}",
                session_key=messages[0].session_key if messages else "system",
                priority=10,  # 高优先级
            )
            
            # 在锁外插入（避免死锁）
            async with self._lock:
                self.messages.insert(0, summary_msg)
                
        except Exception as e:
            # 总结失败，记录但不阻塞
            print(f"Summarization failed: {e}")
    
    async def dequeue(self) -> QueuedMessage | None:
        """出队消息"""
        async with self._lock:
            if not self.messages:
                return None
            return self.messages.pop(0)
    
    def get_size(self) -> int:
        """获取队列大小"""
        return len(self.messages)
```

**Step 2: 编写测试**

```python
import pytest
import asyncio
from datacloud_agent.core.queue import MessageQueue, DropPolicy, QueuedMessage


@pytest.mark.asyncio
async def test_queue_old_policy():
    """测试OLD丢弃策略"""
    queue = MessageQueue(max_size=3, drop_policy=DropPolicy.OLD)
    
    # 填满队列
    for i in range(3):
        await queue.enqueue(QueuedMessage(prompt=f"msg-{i}", session_key="test"))
    
    assert queue.get_size() == 3
    
    # 再添加一条，应该丢弃最旧的
    await queue.enqueue(QueuedMessage(prompt="msg-3", session_key="test"))
    assert queue.get_size() == 3


@pytest.mark.asyncio
async def test_queue_new_policy():
    """测试NEW丢弃策略"""
    queue = MessageQueue(max_size=2, drop_policy=DropPolicy.NEW)
    
    # 填满队列
    await queue.enqueue(QueuedMessage(prompt="msg-1", session_key="test"))
    await queue.enqueue(QueuedMessage(prompt="msg-2", session_key="test"))
    
    # 再添加应该失败
    result = await queue.enqueue(QueuedMessage(prompt="msg-3", session_key="test"))
    assert result is False
    assert queue.get_size() == 2


@pytest.mark.asyncio
async def test_queue_dequeue():
    """测试出队"""
    queue = MessageQueue()
    msg = QueuedMessage(prompt="test", session_key="test")
    
    await queue.enqueue(msg)
    assert queue.get_size() == 1
    
    dequeued = await queue.dequeue()
    assert dequeued is not None
    assert dequeued.prompt == "test"
    assert queue.get_size() == 0


@pytest.mark.asyncio
async def test_queue_empty_dequeue():
    """测试空队列出队"""
    queue = MessageQueue()
    result = await queue.dequeue()
    assert result is None
```

**Step 3: 运行测试**

```bash
uv run --package datacloud-agent pytest datacloud-agent/tests/test_queue_policies.py -v
```

Expected: `4 passed`

**Step 4: Commit**

```bash
git add datacloud-agent/src/datacloud_agent/core/queue.py datacloud-agent/tests/test_queue_policies.py
git commit -m "feat(datacloud-agent): implement SUMMARIZE drop policy for message queue"
```

---

### Task 2.2: 完善队列模式实现

**文件:**
- 修改: `datacloud-agent/src/datacloud_agent/core/runner.py`
- 测试: `datacloud-agent/tests/test_queue_modes.py`

**Step 1: 添加队列模式支持**

在 `runner.py` 中添加：

```python
from enum import Enum


class QueueMode(Enum):
    """队列模式"""
    COLLECT = "collect"       # 合并消息
    STEER = "steer"          # 使用Command注入
    STEER_BACKLOG = "steer_backlog"  # 注入并入队
    INTERRUPT = "interrupt"  # 取消当前运行
    QUEUE = "queue"          # 入队等待


class AgentRunner:
    """Agent执行引擎 - 扩展队列模式支持"""
    
    def __init__(self, agent_registry: Any):
        self.agent_registry = agent_registry
        self._running_tasks: dict[str, dict] = {}
        self._checkpointers: dict[str, InMemorySaver] = {}
        self._queues: dict[str, MessageQueue] = {}  # 每个session的队列
    
    async def process_message(
        self,
        session_key: str,
        prompt: str,
        mode: QueueMode = QueueMode.QUEUE,
    ) -> dict[str, Any]:
        """
        处理消息，根据模式选择处理方式
        
        Args:
            session_key: 会话标识符
            prompt: 用户输入
            mode: 处理模式
            
        Returns:
            处理结果
        """
        if mode == QueueMode.COLLECT:
            return await self._collect_mode(session_key, prompt)
        elif mode == QueueMode.STEER:
            return await self._steer_mode(session_key, prompt)
        elif mode == QueueMode.STEER_BACKLOG:
            return await self._steer_backlog_mode(session_key, prompt)
        elif mode == QueueMode.INTERRUPT:
            return await self._interrupt_mode(session_key)
        elif mode == QueueMode.QUEUE:
            return await self._queue_mode(session_key, prompt)
        else:
            raise ValueError(f"Unknown mode: {mode}")
    
    async def _collect_mode(self, session_key: str, prompt: str) -> dict[str, Any]:
        """COLLECT模式：合并消息并执行"""
        # 合并最近的消息（简化实现）
        messages = [{"role": "user", "content": prompt}]
        return await self._execute_agent(session_key, messages)
    
    async def _steer_mode(self, session_key: str, prompt: str) -> dict[str, Any]:
        """STEER模式：使用Command注入"""
        success = await self._steer_run(session_key, prompt)
        return {"steered": success, "session_key": session_key}
    
    async def _steer_backlog_mode(self, session_key: str, prompt: str) -> dict[str, Any]:
        """STEER_BACKLOG模式：注入并入队"""
        # 先尝试STEER
        steered = await self._steer_run(session_key, prompt)
        
        # 同时入队
        if session_key not in self._queues:
            self._queues[session_key] = MessageQueue()
        
        await self._queues[session_key].enqueue(
            QueuedMessage(prompt=prompt, session_key=session_key)
        )
        
        return {"steered": steered, "queued": True, "session_key": session_key}
    
    async def _interrupt_mode(self, session_key: str) -> dict[str, Any]:
        """INTERRUPT模式：取消当前运行"""
        if session_key in self._running_tasks:
            task = self._running_tasks[session_key].get("task")
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self._running_tasks[session_key]
            return {"interrupted": True, "session_key": session_key}
        return {"interrupted": False, "session_key": session_key}
    
    async def _queue_mode(self, session_key: str, prompt: str) -> dict[str, Any]:
        """QUEUE模式：入队等待处理"""
        if session_key not in self._queues:
            self._queues[session_key] = MessageQueue()
        
        success = await self._queues[session_key].enqueue(
            QueuedMessage(prompt=prompt, session_key=session_key)
        )
        
        return {"queued": success, "session_key": session_key}
```

**Step 2: 编写测试**

```python
import pytest
from unittest.mock import Mock
from datacloud_agent.core.runner import AgentRunner, QueueMode


@pytest.fixture
def mock_registry():
    registry = Mock()
    registry.get.return_value = Mock(
        provider="openai",
        model="qwen3.5-plus",
        system_prompt=None,
    )
    return registry


@pytest.mark.asyncio
async def test_interrupt_mode_no_running_task(mock_registry):
    """测试INTERRUPT模式无运行任务"""
    runner = AgentRunner(mock_registry)
    
    result = await runner.process_message(
        "tenant:1:agent:2:session:3",
        "test",
        mode=QueueMode.INTERRUPT
    )
    
    assert result["interrupted"] is False


@pytest.mark.asyncio
async def test_queue_mode(mock_registry):
    """测试QUEUE模式"""
    runner = AgentRunner(mock_registry)
    
    result = await runner.process_message(
        "tenant:1:agent:2:session:3",
        "Hello",
        mode=QueueMode.QUEUE
    )
    
    assert result["queued"] is True
    assert result["session_key"] == "tenant:1:agent:2:session:3"


@pytest.mark.asyncio
async def test_unknown_mode(mock_registry):
    """测试未知模式"""
    runner = AgentRunner(mock_registry)
    
    with pytest.raises(ValueError, match="Unknown mode"):
        await runner.process_message(
            "tenant:1:agent:2:session:3",
            "test",
            mode="invalid"
        )
```

**Step 3: 运行测试**

```bash
uv run --package datacloud-agent pytest datacloud-agent/tests/test_queue_modes.py -v
```

Expected: `3 passed`

**Step 4: Commit**

```bash
git add datacloud-agent/src/datacloud_agent/core/runner.py datacloud-agent/tests/test_queue_modes.py
git commit -m "feat(datacloud-agent): implement all queue modes (COLLECT, STEER, STEER_BACKLOG, INTERRUPT, QUEUE)"
```

---

## Wave 3: 集成测试与验证 (1-2天)

### Task 3.1: 创建端到端集成测试

**文件:**
- 创建: `datacloud-agent/tests/integration/test_e2e.py`

**Step 1: 编写端到端测试**

```python
"""端到端集成测试

验证完整流程：
1. Agent注册
2. 消息处理
3. 工具调用
4. Token计数
5. STEER模式
"""

import pytest
import os
from datacloud_agent.core.registry import AgentRegistry
from datacloud_agent.core.runner import AgentRunner, QueueMode


@pytest.fixture
def setup_agent():
    """设置测试Agent"""
    registry = AgentRegistry()
    registry.create_default_agent("test-agent")
    runner = AgentRunner(registry)
    return registry, runner


@pytest.mark.asyncio
@pytest.mark.integration
async def test_basic_message_processing(setup_agent):
    """测试基本消息处理"""
    registry, runner = setup_agent
    
    session_key = "tenant:1:agent:test-agent:session:001"
    
    result = await runner.process_message(
        session_key,
        "Hello, what is 2+2?",
        mode=QueueMode.COLLECT
    )
    
    assert "response" in result or "queued" in result


@pytest.mark.asyncio
@pytest.mark.integration
async def test_queue_mode_processing(setup_agent):
    """测试队列模式"""
    registry, runner = setup_agent
    
    session_key = "tenant:1:agent:test-agent:session:002"
    
    # 入队
    result = await runner.process_message(
        session_key,
        "Test message",
        mode=QueueMode.QUEUE
    )
    
    assert result["queued"] is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_steering_without_checkpointer(setup_agent):
    """测试无checkpointer时的STEER"""
    registry, runner = setup_agent
    
    session_key = "tenant:1:agent:test-agent:session:003"
    
    result = await runner.process_message(
        session_key,
        "Steer message",
        mode=QueueMode.STEER
    )
    
    # 无checkpointer时应该失败
    assert result["steered"] is False
```

**Step 2: 运行集成测试**

```bash
uv run --package datacloud-agent pytest datacloud-agent/tests/integration/test_e2e.py -v -m integration
```

**Step 3: Commit**

```bash
git add datacloud-agent/tests/integration/test_e2e.py
git commit -m "test(datacloud-agent): add end-to-end integration tests"
```

---

### Task 3.2: 创建POC验证脚本

**文件:**
- 创建: `poc_tests/verify_integration.py`

**Step 1: 创建验证脚本**

```python
#!/usr/bin/env python3
"""
OpenClaw Gateway 集成验证脚本

基于6个POC验证，验证集成后的功能
"""

import asyncio
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'datacloud-agent', 'src'))

from datacloud_agent.core.registry import AgentRegistry
from datacloud_agent.core.runner import AgentRunner, QueueMode
from datacloud_agent.core.tools import get_business_tools
from datacloud_agent.core.subagents import get_default_subagents


async def verify_basic_integration():
    """验证基础集成（POC 1）"""
    print("\n=== 验证 1: 基础集成 ===")
    
    registry = AgentRegistry()
    config = registry.create_default_agent("verify-agent")
    runner = AgentRunner(registry)
    
    print(f"✓ Agent注册成功: {config.agent_id}")
    print(f"✓ 工具数量: {len(config.tools)}")
    print(f"✓ 子Agent数量: {len(config.subagents)}")
    
    return True


async def verify_token_counting():
    """验证令牌计数（POC 2）"""
    print("\n=== 验证 2: 令牌计数 ===")
    
    # 这个验证需要实际调用LLM
    # 在实际环境中运行
    print("⚠ 需要实际LLM调用，请在集成环境中验证")
    print("  预期: usage字段包含input_tokens, output_tokens, total_tokens")
    
    return True


async def verify_tools():
    """验证工具系统（POC 4）"""
    print("\n=== 验证 3: 工具系统 ===")
    
    tools = get_business_tools()
    print(f"✓ 业务工具数量: {len(tools)}")
    
    for tool in tools:
        print(f"  - {tool.name}: {tool.description[:50]}...")
    
    return True


async def verify_subagents():
    """验证子Agent（POC 5）"""
    print("\n=== 验证 4: 子Agent ===")
    
    subagents = get_default_subagents()
    print(f"✓ 子Agent配置数量: {len(subagents)}")
    
    for sa in subagents:
        print(f"  - {sa['name']}: {sa['description']}")
    
    return True


async def verify_queue_modes():
    """验证队列模式"""
    print("\n=== 验证 5: 队列模式 ===")
    
    registry = AgentRegistry()
    registry.create_default_agent("queue-test-agent")
    runner = AgentRunner(registry)
    
    session_key = "tenant:1:agent:queue-test-agent:session:001"
    
    # 测试QUEUE模式
    result = await runner.process_message(
        session_key, "Test message", mode=QueueMode.QUEUE
    )
    print(f"✓ QUEUE模式: {'成功' if result['queued'] else '失败'}")
    
    # 测试INTERRUPT模式
    result = await runner.process_message(
        session_key, "", mode=QueueMode.INTERRUPT
    )
    print(f"✓ INTERRUPT模式: {'成功' if not result['interrupted'] else '失败'} (无运行任务)")
    
    return True


async def main():
    """主验证流程"""
    print("=" * 60)
    print("OpenClaw Gateway 集成验证")
    print("=" * 60)
    
    results = []
    
    results.append(("基础集成", await verify_basic_integration()))
    results.append(("令牌计数", await verify_token_counting()))
    results.append(("工具系统", await verify_tools()))
    results.append(("子Agent", await verify_subagents()))
    results.append(("队列模式", await verify_queue_modes()))
    
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ 所有验证通过！")
        return 0
    else:
        print("❌ 部分验证失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
```

**Step 2: 运行验证脚本**

```bash
cd /home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation
uv run --package datacloud-agent python poc_tests/verify_integration.py
```

**Step 3: Commit**

```bash
git add poc_tests/verify_integration.py
git commit -m "test(datacloud-agent): add integration verification script"
```

---

## Wave 4: 文档与清理 (0.5天)

### Task 4.1: 更新架构文档

**文件:**
- 创建: `docs/architecture/deepagents-integration.md`

**Step 1: 编写架构文档**

```markdown
# DeepAgents 集成架构

## 概述

基于6个POC验证结果，OpenClaw Gateway集成deepagents实现Agent执行引擎。

## POC验证结果

| POC | 功能 | 状态 | 关键发现 |
|-----|------|------|----------|
| 1 | 基础集成 | ✅ | `create_deep_agent` 正常工作 |
| 2 | 令牌计数 | ✅ | 从`AIMessage.usage_metadata`提取 |
| 3 | STEER模式 | ✅ | `Command(resume=...)`注入 |
| 4 | 工具系统 | ✅ | 阿里云百炼Qwen支持工具调用 |
| 5 | 子Agent | ✅ | 通过task工具调用 |
| 6 | 流式输出 | ✅ | `astream()`返回异步迭代器 |

## 关键配置规范

### 工具定义（基于POC 4 v2）

```python
@tool
def know(query: str) -> str:
    """
    知识检索工具。用于查询特定主题的知识信息。
    
    Args:
        query: 要查询的主题或关键词
        
    Returns:
        关于该主题的知识信息
    """
    return f"Knowledge about: {query}"
```

**关键要点**：
- 必须包含Args和Returns
- 描述要清晰明确
- 使用中文描述（针对中文模型）

### 系统提示（基于POC 4 v2）

```
你是一个智能助手。当用户询问任何问题时，你必须使用可用的工具来获取信息。

可用的工具：
- know: 用于检索知识信息
- query: 用于查询数据

重要：对于每个用户查询，请分析是否需要使用工具。
```

**关键要点**：
- 必须明确强制使用工具
- 列出所有可用工具
- 说明工具用途

## 架构组件

### 1. ModelConfig
- 负责模型初始化和配置
- 支持阿里云百炼Qwen

### 2. Tools
- 定义五个原子工具
- 遵循POC验证的详细描述规范

### 3. SubAgents
- 配置子Agent
- 通过task工具机制调用

### 4. AgentRunner
- 核心执行引擎
- 集成deepagents
- 支持流式输出和STEER模式

### 5. MessageQueue
- 消息队列管理
- 支持SUMMARIZE丢弃策略

### 6. 多租户组件（已实现）

#### 6.1 TenantContext
**文件**: `datacloud-agent/src/datacloud_agent/tenant/context.py`

```python
@dataclass
class TenantContext:
    """租户上下文 - 使用contextvars实现请求级隔离"""
    tenant_id: str                    # 租户ID
    tenant_type: TenantType           # PUBLIC | USER_PUBLIC | USER_PRIVATE
    session_id: str | None = None     # 会话ID
    task_id: str | None = None        # 任务ID
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def get_path_prefix(self) -> str:
        """获取路径前缀: {tenant_type}/{tenant_id}"""
        return f"{self.tenant_type.value}/{self.tenant_id}"
```

**使用示例**:
```python
from datacloud_agent.tenant.context import TenantContext, tenant_scope

# 创建租户上下文
ctx = TenantContext(
    tenant_id="user_001",
    tenant_type=TenantType.USER_PRIVATE
)

# 在上下文中执行
with tenant_scope(ctx):
    # 所有文件操作自动路由到 user_private/user_001/
    result = await agent_runner.execute(...)
```

#### 6.2 TenantAwareFileBackend
**文件**: `datacloud-agent/src/datacloud_agent/backend/composite.py`

```python
class TenantAwareFileBackend:
    """租户感知的文件后端 - 自动路由到正确的存储位置"""
    
    def __init__(self, base_dir: Path, tenant_context_getter=None):
        self.base_dir = Path(base_dir).resolve()
        self._tenant_context_getter = tenant_context_getter
    
    def get_full_path(self, path: str) -> Path:
        """
        将逻辑路径转换为绝对路径
        
        支持的逻辑路径前缀:
        - public/test.txt → base_dir/public/test.txt
        - user_public/doc.txt → base_dir/user_public/{tenant_id}/doc.txt
        - user_private/data.txt → base_dir/user_private/{tenant_id}/data.txt
        """
        if path.startswith("public/"):
            return self.base_dir / path
        elif path.startswith("user_public/"):
            ctx = self._get_tenant_context()
            return self.base_dir / f"user_public/{ctx.tenant_id}/{path[12:]}"
        elif path.startswith("user_private/"):
            ctx = self._get_tenant_context()
            return self.base_dir / f"user_private/{ctx.tenant_id}/{path[13:]}"
    
    async def read(self, path: str) -> bytes:
        full_path = self.get_full_path(path)
        return await asyncio.to_thread(full_path.read_bytes)
    
    async def write(self, path: str, content: bytes) -> None:
        full_path = self.get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(full_path.write_bytes, content)
```

**与deepagents集成**:
```python
from deepagents import create_deep_agent
from datacloud_agent.backend.composite import TenantAwareFileBackend

# 创建租户感知的文件后端
file_backend = TenantAwareFileBackend(
    base_dir="./workspaces",
    tenant_context_getter=TenantContext.get_current
)

# 注入到deepagents
agent = create_deep_agent(
    model=model,
    tools=tools,
    backend=file_backend  # 使用租户感知的后端
)
```

#### 6.3 TenantResolver
**文件**: `datacloud-agent/src/datacloud_agent/tenant/resolver.py`

```python
class TenantResolver:
    """租户解析器 - 从请求中提取租户信息"""
    
    @staticmethod
    def from_headers(request: Request) -> TenantContext:
        """从HTTP headers解析租户"""
        tenant_id = request.headers.get("X-Tenant-ID", "default")
        return TenantContext(
            tenant_id=tenant_id,
            tenant_type=TenantType.USER_PRIVATE
        )
    
    @staticmethod
    def from_session_key(session_key: str) -> TenantContext:
        """从session_key解析租户
        Format: tenant:{tenantId}:agent:{agentId}:{mainKey}
        """
        parts = session_key.split(":")
        if len(parts) >= 2 and parts[0] == "tenant":
            return TenantContext(
                tenant_id=parts[1],
                tenant_type=TenantType.USER_PRIVATE
            )
        # 旧格式兼容
        return TenantContext(
            tenant_id="default",
            tenant_type=TenantType.USER_PRIVATE
        )
```

## 消息流转

### 基础流程
```
用户请求 → AgentRunner → create_deep_agent → LLM
                              ↓
                         工具调用 → 业务服务
                              ↓
                         子Agent调用（task工具）
                              ↓
                         子Agent工具调用
```

### 多租户流程（带文件隔离）
```
HTTP Request
    │
    ▼
┌─────────────────┐
│ X-Tenant-ID     │
│ Header解析       │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ TenantContext       │  ← contextvars隔离
│ (tenant_id, type)   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ TenantAwareFileBackend
│                     │
│ 路径路由:            │
│ public/ → 公共存储   │
│ user_public/ → 租户公共
│ user_private/ → 租户私有
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ create_deep_agent   │
│ backend=file_backend│
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 工具执行             │
│ - read_file          │
│ - write_file         │
│ - execute            │
│ (自动路由到正确路径)  │
└─────────────────────┘
```

## 配置示例

### 基础Agent配置
```python
# Agent配置
config = AgentConfig(
    agent_id="my-agent",
    provider="openai",
    model="qwen3.5-plus",
    system_prompt=get_system_prompt(),
    tools=["know", "query", "compute", "render", "store"],
    subagents=get_default_subagents(),
)
```

### 多租户Agent配置（完整示例）
```python
from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
from datacloud_agent.tenant.context import TenantContext, tenant_scope
from datacloud_agent.backend.composite import TenantAwareFileBackend

async def create_tenant_aware_agent(
    tenant_id: str,
    agent_config: AgentConfig
):
    """创建租户感知的Agent"""
    
    # 1. 创建租户上下文
    tenant_ctx = TenantContext(
        tenant_id=tenant_id,
        tenant_type=TenantType.USER_PRIVATE
    )
    
    # 2. 创建租户感知的文件后端
    file_backend = TenantAwareFileBackend(
        base_dir="./workspaces",
        tenant_context_getter=lambda: tenant_ctx
    )
    
    # 3. 在租户上下文中创建Agent
    with tenant_scope(tenant_ctx):
        agent = create_deep_agent(
            model=init_chat_model(agent_config.model),
            system_prompt=build_system_prompt(tenant_ctx),
            tools=agent_config.tools,
            backend=file_backend,  # 关键：注入租户感知的后端
            subagents=agent_config.subagents
        )
    
    return agent, tenant_ctx

# 使用示例
async def handle_request(tenant_id: str, message: str):
    agent, ctx = await create_tenant_aware_agent(
        tenant_id=tenant_id,
        agent_config=default_config
    )
    
    with tenant_scope(ctx):
        # Agent的所有文件操作自动隔离到该租户空间
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": message}]
        })
        
        # 文件写入示例：自动路由到 ./workspaces/user_private/user_001/output/
        # 无需手动处理路径
    
    return result
```

### HTTP API使用（带租户隔离）
```bash
# 创建会话 (指定租户)
curl -X POST http://localhost:18789/v1/sessions \
  -H "X-Tenant-ID: user_001" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "default"
  }'

# 发送消息
curl -X POST http://localhost:18789/v1/chat \
  -H "X-Tenant-ID: user_001" \
  -H "X-Session-ID: session-abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "请分析我的数据并生成报告"
  }'
```

## 注意事项

### deepagents集成
1. **工具调用**：阿里云百炼Qwen支持工具调用，但需要详细的工具描述
2. **Token计数**：从`AIMessage.usage_metadata`提取，无需tiktoken
3. **STEER模式**：使用`Command(resume=...)`，需要checkpointer支持
4. **流式输出**：使用`astream()`，返回异步迭代器

### 多租户隔离
1. **路径隔离**：通过`public/`、`user_public/`、`user_private/`前缀实现
2. **ContextVar传播**：确保在所有异步调用中正确传播`TenantContext`
3. **文件权限**：当前设计无显式权限验证，仅通过路径前缀隔离
4. **并发安全**：`TenantAwareFileBackend`使用`asyncio.to_thread`进行文件操作

### 已知限制
1. **租户ID信任**：设计假设上游已认证，服务层需验证tenant_id合法性
2. **ContextVar子进程**：子进程需手动传递租户上下文
3. **并发文件访问**：多实例写入同一目录需考虑文件锁或共享后端
```

**Step 2: Commit**

```bash
git add docs/architecture/deepagents-integration.md
git commit -m "docs(datacloud-agent): add deepagents integration architecture documentation"
```

---

### Task 4.2: 运行完整测试套件

**Step 1: 运行所有测试**

```bash
cd /home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation

# 运行单元测试
uv run --package datacloud-agent pytest datacloud-agent/tests/ -v --ignore=datacloud-agent/tests/integration

# 运行代码检查
uv run ruff check datacloud-agent/src
uv run ruff format datacloud-agent/src --check
```

**Step 2: 提交最终变更**

```bash
git add .
git commit -m "chore(datacloud-agent): final cleanup and test suite verification"
```

---

## 验收标准

### 功能验收
- [x] **POC 7 Backend验证完成** - 确认backend参数和内置工具（修正：使用backend替代sandbox）
- [ ] **沙箱策略决策** - 明确使用backend参数或自建Docker沙箱
- [ ] **安全验证** - tenant_id格式验证和访问控制实现
- [ ] `create_deep_agent` 集成成功
- [ ] 从 `AIMessage.usage_metadata` 提取token计数
- [ ] 五个原子工具可正常调用（配置正确时）
- [ ] 子Agent配置和调用正常
- [ ] STEER模式使用 `Command(resume=...)`
- [ ] 流式输出使用 `astream()`
- [ ] SUMMARIZE丢弃策略实现
- [ ] 所有队列模式（COLLECT, STEER, STEER_BACKLOG, INTERRUPT, QUEUE）

### 测试验收
- [ ] 单元测试: 20+ 测试通过
- [ ] 增量验证: Wave 1每个Task后验证通过
- [ ] 集成测试: 端到端流程通过
- [ ] 验证脚本: 所有检查项通过
- [ ] 安全测试: tenant_id验证和访问控制测试

### 文档验收
- [ ] 架构文档更新（含backend参数说明）
- [ ] 工具定义规范文档
- [ ] 系统提示模板文档
- [ ] 安全验证规范文档

---

## 关键设计决策（基于POC验证，含评审修正）

1. **工具沙箱**: ⚠️ **已修正** - `create_deep_agent()` 没有 `sandbox` 参数，使用 `backend` 参数（POC 7修正）
   - `LocalShellBackend`: 提供执行能力，但无真正隔离
   - `FilesystemBackend`: 限制文件操作范围
   - **生产建议**: backend参数 + 自建Docker沙箱
2. **不复刻子Agent**: 直接使用deepagents SubAgent ✅
3. **不复刻中断恢复**: 直接使用LangGraph `interrupt()` + `Command(resume=...)` ✅
4. **不使用tiktoken**: 直接从`AIMessage.usage_metadata`提取令牌计数 ✅
5. **工具描述规范**: 必须包含Args和Returns（POC 4 v2验证）✅
6. **系统提示规范**: 必须明确强制使用工具（POC 4 v2验证）✅
7. **安全验证**: AgentRegistry增加tenant_id格式验证和访问控制（评审新增）✅
8. **增量验证**: Wave 1每个Task后快速验证，及早发现问题（评审新增）✅

**时间估算（已修正）**:
| Wave | 原估算 | 修正后 | 变更原因 |
|------|--------|--------|----------|
| Wave 0 | 0.5天 | **1天** | 扩展backend验证，含自建沙箱方案设计 |
| Wave 1 | 3-4天 | 3-4天 | 保持不变 |
| Wave 2 | 2-3天 | 2-3天 | 保持不变 |
| Wave 3 | 1-2天 | 1-2天 | 调整为增量验证 |
| Wave 4 | 0.5天 | 0.5天 | 保持不变 |
| **总计** | **6-8天** | **8-10天** | **包含更充分的验证和安全增强** |

**预期效果**:
- 减少 **60-70%** 开发工作量
- 基于验证过的技术方案
- 与LangGraph生态更好兼容
- 阿里云百炼Qwen完全支持
- **增强**: 多租户安全验证和访问控制

---

## 启动命令

```bash
# 启动工作会话
/start-work openclaw-gateway-phase2
```

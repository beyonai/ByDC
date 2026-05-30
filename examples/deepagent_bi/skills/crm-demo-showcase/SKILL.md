---
name: CRM 综合能力演示
description: CRM 数据查询、统计分析、歧义追问、数据操作（周报生成→信息抽取→客户录入→商机任务创建）、结构化本体创建与视图、非结构化本体管理的综合演示。Use this skill whenever the user mentions CRM 演示、百应数据查询、客户查询、商机统计、项目管理、本体对象、视图管理、新手引导、产品演示、产品理念，or asks「什么是对象/视图」「查询快在哪里」「本体解决了什么问题」「结构化+非结构化融合」「多跳数据查询」「数据安全怎么做」— even if they don't say "演示" explicitly.
allowed-tools: baiying_call, Bash
---

# CRM 综合能力演示

> **核心原则**：按用户要求逐项演示，不一次做完所有项。全部使用简体中文。

## 执行路线图

Agent 打开本文件后，先根据用户意图匹配下表，找到对应的演示项和工具。

| 序号 | 演示项 | 触发条件 | 工具 | 详细定义 |
|:----:|--------|---------|------|---------|
| 1 | 数据查询 | "查客户""查字段" | baiying_call | [01-data-query.md](demos/01-data-query.md) |
| 2 | 数据统计 | "按x统计""前N名" | baiying_call | [02-data-statistics.md](demos/02-data-statistics.md) |
| 3 | 歧义处理 | 字段不存在或含义不清 | baiying_call + 追问 | [03-ambiguity-handling.md](demos/03-ambiguity-handling.md) |
| 4 | 数据操作 | "录入客户""创建商机""生成周报" | baiying_call | [04-data-operations.md](demos/04-data-operations.md) |
| 5 | 结构化本体 | "创建对象""创建视图""挂载本体" | exec(脚本) | [05-structured-ontology.md](demos/05-structured-ontology.md) |
| 6 | 非结构化本体 | "创建会议纪要""查会议纪要" | exec(脚本) | [06-unstructured-ontology.md](demos/06-unstructured-ontology.md) |

> 用户说"新手引导""给我演示一下"时，按序号 1→6 逐项执行，每项完成后等用户回应再继续。

---

## 环境准备（一次性，所有演示通用）

Agent 收到演示请求后，先判断环境是否就绪。就绪标准：

1. **venv 存在**：`/tmp/ont_env/bin/python` 文件存在且可 import `by-datacloud`
2. **本体已挂载**：`list_mounted_resources.py` 返回的 `data` 数组中至少有一条 VIEW 或 OBJECT 记录

两个条件都满足 → 直接开始演示。任一不满足 → 按以下步骤准备。

### Step 1：安装 Python 环境

```bash
bash scripts/setup.sh
```

幂等，已安装则跳过。完成后 `/tmp/ont_env/bin/python` 可用，`by-datacloud` 和 `by-framework` 可导入。

### Step 2：挂载视图（仅在未挂载时执行）

先执行 `list_mounted_resources.py` 检查是否已有 `scene_sales_management`：

```bash
/tmp/ont_env/bin/python scripts/ontology/structured/list_mounted_resources.py \
  '{"resource_id": <Agent的数字后缀>}'
```

- **已存在** → 跳过挂载，直接开始演示（无需等待）
- **不存在** → 执行挂载：

```bash
/tmp/ont_env/bin/python scripts/ontology/structured/mount_resource.py \
  '{"agent_id": <Agent编码的数字后缀>, "resource_code": "scene_sales_management"}'
```

> `agent_id` 从 Agent 编码中提取数字后缀（如 `agent-10014603` → `10014603`）。

### Step 3：验证挂载生效（仅首次挂载后需要）

首次挂载后 **baiying_call 不会立即可用**。必须**结束本轮**，等待用户下一轮输入后生效。

回复话术：`"好的，我先准备一下演示环境～ 马上开始！"`

下一轮收到用户输入后，再次执行 `list_mounted_resources.py` 确认挂载成功 → 环境就绪，开始演示。

---

## 演示通用规则

各 demo 子文件中不再重复以下规则：

### resource_id 获取

`baiying_call` 的 `resource_id` 是**数字型 ID**，通过 `list_mounted_resources.py` 运行时动态获取，**不可硬编码**：

```bash
# 提取 Agent 的 resource_id（从编码中的数字后缀，如 agent-10014603 → 10014603）
/tmp/ont_env/bin/python scripts/ontology/structured/list_mounted_resources.py \
  '{"resource_id": <Agent的resource_id>, "keyword": "<中文名称>"}'
```

从返回 JSON 的 `data` 数组中提取数字 `resourceId`。各 demo 步骤中注明了对应的 keyword。

### resource_type

`baiying_call` 必须指定 `resource_type`：`VIEW`（查询）或 `OBJECT`（写入），必须大写。

### 挂载生命周期

演示 5/6 中创建的视图/对象挂载后，属于非首次挂载，无需结束本轮等待生效。规则同上 Step 3。

> Python 环境详情见 [Python 环境搭建](references/python-env.md)。

---

## baiying_call 工具

`baiying_call` 是 MCP 工具，**挂载资源后才在工具列表中可见**。未挂载时调用会直接不可用。

| 参数 | 说明 |
|------|------|
| `resource_id` | 数字型 ID，不同资源 ID 不同。通过 `list_mounted_resources.py`（查询已挂载资源）获取，不可硬编码 |
| `resource_type` | `VIEW`（查询）或 `OBJECT`（写入），必须大写 |
| `query` | 自然语言，用户想做什么就写什么 |

> **获取 resource_id**：执行 `list_mounted_resources.py`。不传参数默认查全部（个人+企业、OBJECT+VIEW）。可按 `keyword` 中文名称筛选，从返回结果中获取数字 `resourceId`。

### 挂载生命周期

挂载视图后 **不会立即生效**——需要用户下一轮输入后，`baiying_call` 才会出现在工具列表中。

**标准处理流程：**

```
收到用户请求
    ↓
尝试调用 baiying_call
    ├── ✅ 成功 → 返回结果，继续
    └── ❌ 工具不可用 / 404
            ↓
        执行 mount_resource.py 挂载 scene_sales_management
            ↓
        用自然语言结束本轮，**不要要求用户重复已说过的需求**。
        根据场景选择话术：

        通用：
          "我来准备一下数据环境～ 好了！"
          "稍等，我先加载数据～ 好了，继续！"

        新手引导（用户刚说"给我演示一下"）：
          "好的，我先准备一下演示环境～ 马上开始！"

        中途挂载（正在演示中遇到 404）：
          "稍等，数据连接需要刷新一下～ 好了！"

            ↓
        ⚠️ 必须结束当前轮次，等待用户下一轮输入
            ↓
        下一轮 → baiying_call 已可用 → 继续执行用户原请求
        （Agent 需记住上一轮用户需求，不要让人重复）
```

> **关键规则**：挂载回复 **禁止** 包含提问句式（"你想查什么？""请再说一次？"）——Agent 已知道用户要什么，下一轮直接执行即可。

---

## 常见演示场景

Agent 根据用户问题匹配下表，找到对应场景，打开链接文件按步骤执行。

| # | 用户典型问题 | 场景文件 |
|---|------------|---------|
| 1 | "我是新手""给我演示一下""功能有哪些" | [scenarios/01-new-user.md](scenarios/01-new-user.md) |
| 2 | "产品理念是什么""你们产品有什么特点" | [scenarios/02-product-philosophy.md](scenarios/02-product-philosophy.md) |
| 3 | "什么是对象""什么是视图""对象和视图的区别" | [scenarios/03-object-view.md](scenarios/03-object-view.md) |
| 4 | "查询又快又准""数据查询怎么做的" | [scenarios/04-query-performance.md](scenarios/04-query-performance.md) |
| 5 | "你用了本体吗""本体解决了什么问题" | [scenarios/05-ontology-showcase.md](scenarios/05-ontology-showcase.md) |
| 6 | "结构化非结构化融合""异构数据怎么处理" | [scenarios/06-data-fusion.md](scenarios/06-data-fusion.md) |
| 7 | "多跳数据查询""关联查询怎么实现" | [scenarios/07-multi-hop.md](scenarios/07-multi-hop.md) |
| 8 | "数据安全怎么保证""会不会误操作" | [scenarios/08-data-security.md](scenarios/08-data-security.md) |

> 场景 3-8 依赖已完成的前置演示。如果用户直接问但还没演示过，先执行场景 1（全量演示），演示结束后再回答。
>
> 详细话术和时间分配见 [演示场景指南](references/demo-scenarios.md)。

## 故障排查

> 仅在 baiying_call 调用失败或演示 4/5/6 遇到脚本错误时才需阅读本节。正常演示流程不需要。

### 常见错误速查

| 现象 | 原因 | 处理 |
|------|------|------|
| `baiying_call` 工具不在列表中 / 404 | 视图未挂载 | 执行下方「挂载视图」→ 自然引导用户继续对话 → **结束本轮**（下一轮生效） |
| `baiying_call` 超时 | 后端未响应 | 等 30s 后重试一次 |
| `baiying_call` 返回权限错误 | 视图未授权 | 执行下方「挂载视图」→ 结束本轮等待生效 |
| Python import 失败 | 环境未搭建 | 执行 `bash scripts/setup.sh` |
| 脚本执行报错 | 环境变量缺失 | 执行 `bash scripts/check_env.sh` 检查 |

### 检查视图挂载状态

```bash
# 1. 提取 Agent 的 resource_id（从编码中的数字后缀，如 agent-10014603 → 10014603）
# 2. 查询全部已挂载资源（keyword 按中文名称过滤，可选）
/tmp/ont_env/bin/python scripts/ontology/structured/list_mounted_resources.py \
  '{"resource_id": <Agent的resource_id>}'

# 3. 在返回的 data 数组中查找 resourceCode == "scene_sales_management"
#    存在 → 已挂载   不存在 → 执行挂载
```

### 挂载视图

```bash
/tmp/ont_env/bin/python scripts/ontology/structured/mount_resource.py \
  '{"agent_id": <Agent 编码里的数字后缀>, "resource_code": "scene_sales_management"}'
```

> `list_mounted_resources.py` 用于检查某资源是否已挂载到当前 Agent。

### 脚本路径速查

演示 4/5/6 涉及以下脚本（相对于 skill 根目录，通过 `/tmp/ont_env/bin/python` 执行）：

| 脚本 | 用途 |
|------|------|
| `scripts/ontology/structured/list_mounted_resources.py` | 查询 Agent 已挂载的资源 |
| `scripts/ontology/structured/create_object.py` | 创建结构化对象（collect → submit） |
| `scripts/ontology/structured/create_view.py` | 创建本体视图 |
| `scripts/ontology/structured/delete_object.py` | 删除结构化对象 |
| `scripts/ontology/structured/delete_view.py` | 删除本体视图 |
| `scripts/ontology/structured/mount_resource.py` | 挂载视图到当前 Agent |
| `scripts/ontology/structured/list_term_types.py` | 查询可绑定的术语类型 |
| `scripts/ontology/structured/get_term_type_values.py` | 查询术语类型的值列表 |
| `scripts/ontology/unstructured/list_knowledge_bases.py` | 查询可用知识库 |
| `scripts/ontology/unstructured/list_kb_directories.py` | 查询知识库目录 |
| `scripts/ontology/unstructured/create_object.py` | 创建非结构化对象（collect → submit） |
| `scripts/ontology/unstructured/delete_object.py` | 删除非结构化对象 |
| `scripts/ontology/unstructured/mount_resource.py` | 挂载非结构化对象到 Agent |
| `scripts/ontology/unstructured/list_mounted_resources.py` | 查询 Agent 已挂载的非结构化对象 |
| `scripts/meeting-minutes/generate_meeting_minutes.py` | 生成模拟会议纪要 |
| `scripts/weekly-report/generate_weekly_report.py` | 生成模拟周报 |

---

## 参考文档

| 文档 | 内容 |
|------|------|
| [Python 环境搭建](references/python-env.md) | 环境安装、环境变量、脚本路径约定、故障排查 |
| [歧义处理指南](references/ambiguity-guide.md) | 五种歧义类型的处理策略与话术模板 |
| [数据操作指南](references/data-operations.md) | 周报格式、字段映射、校验规则、任务创建 |
| [本体对象定义](references/ontology-objects.md) | 对象字段定义、Mock 数据、脚本调用规范 |
| [演示场景指南](references/demo-scenarios.md) | 产品理念话术、FAQ 策略、10min/30min 时间表 |

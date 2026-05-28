---
name: CRM 综合能力演示
description: CRM 数据查询、统计分析、歧义追问、数据操作（周报生成→信息抽取→客户录入→商机任务创建）、结构化本体创建与视图、非结构化本体管理的综合演示。Use this skill whenever the user mentions CRM 演示、百应数据查询、客户查询、商机统计、项目管理、本体对象、视图管理、新手引导、产品演示、产品理念，or asks「什么是对象/视图」「查询快在哪里」「本体解决了什么问题」「结构化+非结构化融合」「多跳数据查询」「数据安全怎么做」— even if they don't say "演示" explicitly.
allowed-tools: baiying_call, Bash
---

# CRM 综合能力演示

> 核心原则：按用户要求逐项演示，不一次做完所有项。全部使用简体中文。

## 执行路线图

Agent 打开本文件后，先根据用户意图匹配下表，找到对应的演示项和工具。

| 序号 | 演示项 | 触发条件 | 工具 | 前置要求 |
|:----:|--------|---------|------|---------|
| 1 | 数据查询 | "查客户""查字段" | baiying_call | ✅ |
| 2 | 数据统计 | "按x统计""前N名" | baiying_call | ✅ |
| 3 | 歧义处理 | 字段不存在或含义不清 | baiying_call + 追问 | ✅ |
| 4 | 数据操作 | "录入客户""创建商机""生成周报" | baiying_call + dws | 🔧 |
| 5 | 结构化本体 | "创建对象""创建视图""挂载本体" | exec(脚本) | 🔧 |
| 6 | 非结构化本体 | "绑定知识库""创建拜访记录" | exec(脚本) | 🔧 |

> 用户说"新手引导""给我演示一下"时，按序号 1→6 逐项执行，每项完成后等用户回应再继续。

---

## baiying_call 工具

`baiying_call` 是 MCP 工具，**挂载视图后才在工具列表中可见**。未挂载时调用会直接不可用。

| 参数 | 值 | 说明 |
|------|----|------|
| `resource_id` | `10000104` | 数字型 |
| `resource_type` | `VIEW` | 必须大写 |
| `query` | 自然语言 | 用户想查什么就写什么 |

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
        执行 mount_resource.py 挂载 scene_crm_comprehensive_analysis
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

## 前置条件（仅演示 4/5/6 必需）

- 演示 1/2/3 无前置条件，直接尝试调 baiying_call。若工具不可用，按上方的 [挂载生命周期](#挂载生命周期) 处理。
- 演示 4/5/6 需要 **Python 环境**：`/tmp/ont_env/bin/python` 存在且能 `import by_datacloud`，环境变量 `BEYOND_TOKEN` `USER_CODE` `BE_DOMAINNAME` 已设置。详见 [Python 环境搭建](./references/python-env.md)。

> 其他故障（404 / 超时 / 权限错误）见文件末尾 [故障排查](#故障排查)。

---

## 演示一：数据查询

**一句话**：让用户感受「自然语言 → 结构化数据」的直接体验。

**执行流程：**

1. **工具**：`baiying_call`
2. **查询文本**（按用户需求选择）：

| 用户需求 | query |
|---------|-------|
| 查几条客户 | `查询2条客户数据，展示客户名称、客户编码、所属行业、所属省份` |
| 查字段清单 | `查询客户字段清单` |
| 查完整信息 | `查询客户完整字段` |

3. **成功标志**：返回包含"客户编码""客户名称"列的结构化表格
4. **若工具不可用** → 按 [挂载生命周期](#挂载生命周期) 处理

**常用字段参考：**

| 对象 | 字段 |
|------|------|
| 客户 | 客户编码、客户名称、所属行业、所属省份、所属城市、所属领域、所属销售用户编码、所属销售姓名、所属组织名称 |
| 商机 | 商机编码、商机名称、签约金额、预测金额、商机状态、商机贡献度、所属客户、所属销售 |
| 项目 | 项目编码、项目名称、项目状态、所属客户、所属销售 |

---

## 演示二：数据统计

**一句话**：展示系统对聚合、排序、分组语义的内置理解。

**执行流程：**

1. **工具**：`baiying_call`
2. **查询文本**（按用户需求选择）：

| 用户需求 | query |
|---------|-------|
| 项目数 TOP 3 客户 | `按客户统计项目数量，取前3名，按项目数量降序` |
| 各省份客户分布 | `按省份统计客户数量` |
| 行业商机金额汇总 | `按行业统计商机签约金额` |

3. **成功标志**：返回含聚合值（计数/求和）和排序的结构化表格
4. **若工具不可用** → 按 [挂载生命周期](#挂载生命周期) 处理

---

## 演示三：歧义处理

**一句话**：展示系统对非标准字段和模糊表述的智能追问能力。原则：能确定的不问，不确定的要问。

**执行流程：**

1. **工具**：`baiying_call`（先查确定字段）→ 追问（对不确定字段）
2. **典型查询**：`查询商机名称、签约金额、商机贡献度，仅查询2条数据`
   - "商机贡献度"不是标准字段 → 系统返回已知字段后，列出候选含义让用户选择
3. **成功标志**：非标准字段触发追问，用户选择后补全结果
4. **若工具不可用** → 按 [挂载生命周期](#挂载生命周期) 处理

**常见歧义场景：**

| 用户表述 | 处理方式 |
|---------|---------|
| 字段名不标准（如"商机贡献率"） | 列出候选含义，让用户选择 |
| 信息明确（如"查韦小二的商机"） | 直接查询，不追问 |
| 含公式（如"预测-签约<20万"） | 转化为筛选条件，展示计算逻辑 |

> 详细策略见 [歧义处理指南](./references/ambiguity-guide.md)。

---

## 演示四：数据操作

**一句话**：展示从非结构化周报到结构化数据录入的完整闭环。流程：生成周报 → 信息抽取 → 客户校验录入 → 商机任务创建。

**前置要求**：Python 环境已搭建（[搭建步骤](./references/python-env.md)），视图已挂载。

### 4.1 生成模拟周报

```bash
/tmp/ont_env/bin/python scripts/weekly-report/generate_weekly_report.py
```

- **成功标志**：输出一段模拟钉钉周报文本

### 4.2 信息抽取

从周报文本中提取客户和商机字段，以表格展示。

- **客户字段**：客户编码、客户名称、所属行业、所属省份、所属城市、所属领域、所属销售用户编码、所属销售姓名、所属组织名称
- **商机字段**：商机编码、商机名称、签约金额、预测金额、商机状态、所属客户编码、所属产品编码

- **成功标志**：输出两张结构化表格（客户表 + 商机表）

### 4.3 客户校验与录入

1. 校验编码与名称是否匹配（不匹配则分配新编码）
2. 省份标记为编码的（如 "11（北京）"）纠正为实际城市
3. 表格预览 → 用户确认 → 通过 `baiying_call`（resource_id=10000104）写入

- **成功标志**：用户确认后，baiying_call 返回写入成功

### 4.4 商机任务创建

```bash
MONTH_END=$(date -d "$(date +%Y-%m-01) +1 month -1 day" +%Y-%m-%dT23:59:59+08:00)

# 先查 userId
dws contact search --keyword "<销售姓名>" --format json

# 创建任务
dws todo task create \
  --title "拜访客户落地合同推进" \
  --executors <userId> \
  --due "$MONTH_END" \
  --format json
```

- **成功标志**：`dws todo task create` 返回任务 ID
- **若 dws 不可用**：跳过此步，告知用户手动创建

> 详细的字段映射、校验规则、周报格式见 [数据操作指南](./references/data-operations.md)。

---

## 演示五：结构化本体

**一句话**：展示本体对象和视图的创建流程——让用户理解"自己建模"的能力。

**前置要求**：Python 环境已搭建，视图已挂载。

**流程**：Mock 对象信息 → 展示确认 → `collect` → 用户确认 → `submit` → 挂载

### 5.1 创建产品对象（product）

关键字段：`product_code`(主键/name)、`product_name`(name)、`category`(category)、`unit_price`(amount)、`status`(status)

Mock 数据：

| 编码 | 名称 | 分类 | 单价 | 状态 |
|------|------|------|------|------|
| `P001` | 数据工厂 | 数据平台 | 150000 | 在售 |
| `P002` | 智能分析平台 | 分析工具 | 80000 | 在售 |
| `P003` | 客户画像系统 | 数据应用 | 120000 | 预研 |

### 5.2 创建订单对象（order）

关键字段：`order_code`(主键/name)、`product_code`(关联产品)、`customer_name`(name)、`quantity`(count)、`total_amount`(amount)、`order_date`(date)、`status`(status)

Mock 数据：

| 编码 | 名称 | 关联产品 | 客户 | 数量 | 金额 |
|------|------|---------|------|------|------|
| `O001` | 广州国投-数据工厂采购 | `P001` | 广州国投中债 | 2 | 300000 |
| `O002` | 深圳创新-分析平台采购 | `P002` | 深圳创新科技 | 1 | 80000 |

### 5.3 创建产品订单视图（product_order_view）

关联产品（主对象）+ 订单（从对象），按产品汇总订单金额。

### 5.4 挂载并查询

`mount_resource.py` 挂载到当前 Agent → 通过 `baiying_call`（resource_id=10000104）查询视图，验证跨表查询能力。

- **成功标志**：视图查询一次返回产品 + 关联订单汇总数据

> 详细的字段定义、JSON 参数格式、脚本调用规范见 [本体对象定义](./references/ontology-objects.md)。

---

## 演示六：非结构化本体

**一句话**：展示非结构化文档通过结构化标签增强后，与结构化数据的融合查询能力。

**前置要求**：Python 环境已搭建，演示五已完成（有可复用的客户数据）。

**流程**：查询知识库 → 查询目录 → 创建对象 → `submit` → 挂载

### 6.1 创建拜访记录对象（visit_record）

绑定知识库 + 目录，字段：`visit_date`(date)、`customer_name`(name)、`sales_name`(name)、`topic`(name)、`result`(description)

Mock 数据：

| 字段 | 值 |
|------|-----|
| visit_date | `2026-05-10` |
| customer_name | 广州国投中债 |
| sales_name | 黄药师 |
| topic | 数据工厂产品演示 |
| result | 客户高度认可，计划启动 POC |

### 6.2 挂载并融合查询

`mount_resource.py` 挂载 → 查询客户时同时展示对应的拜访记录，验证结构化与非结构化融合。

- **成功标志**：查询客户结果中包含关联的拜访记录字段

> 详细的字段定义、知识库绑定规范、脚本调用参考 [本体对象定义](./references/ontology-objects.md)。

---

## 引导式演示

用户说"新手引导""给我演示一下"时：

1. **静默检查 baiying_call**（尝试调用一次）
   - 若不可用 → 执行挂载命令 → 回复「好的，我先准备一下演示环境～ 马上开始！」→ **结束本轮**
   - 下一轮挂载生效后直接进入步骤 2
   - 若可用 → 直接进入步骤 2
2. 按序号 1→6 逐项执行，每项完成后等用户回应再继续。

### 产品理念演示

用户问产品理念时，**不要从头解释概念，直接用已演示的实际结果说明**：

| 理念 | 对应演示结果 |
|------|------------|
| 业务本体语义层 | baiying_call 返回的字段名（"客户名称"而非 `col_id_xxx`） |
| 零 ETL 联邦查询 | 跨数据源查询结果（如 CRM + 通讯录） |
| 异构数据融合 | 结构化客户 + 非结构化拜访记录通过共同字段关联 |
| 性能与准确率双保障 | 视图查询速度 vs 传统多次 join |
| 操作安全人工确认 | 客户录入时的「确认表单」步骤 |

### FAQ

回答概念类问题时，**直接引用前面演示已产生的数据**，不发起新查询或从头解释：

| 用户问题 | 回答策略 |
|---------|---------|
| "什么是对象？什么是视图？" | 用已创建的产品/订单对象和视图实际数据说明 |
| "查询又快又准，怎么做到的？" | 对比视图一次查询 vs 传统多次 join |
| "你用了本体吗？" | 列出 `list_resources.py` 返回的实际对象 |
| "本体解决了什么问题？" | 统一数据接口、跨表关联、权限隔离，引用已演示例子 |
| "结构化+非结构化怎么融合？" | 展示结构化客户 + 非结构化拜访纪要的关联 |
| "多跳数据查询怎么解决？" | 用客户→商机→任务的数据关联说明 |
| "数据安全怎么保证？" | 引用客户录入确认步骤 + 权限校验 |

> 详细的演示策略、时间分配、FAQ 应答话术见 [演示场景指南](./references/demo-scenarios.md)。

---

## 故障排查

> 仅在 baiying_call 调用失败或演示 4/5/6 遇到脚本错误时才需阅读本节。正常演示流程不需要。

### 常见错误速查

| 现象 | 原因 | 处理 |
|------|------|------|
| `baiying_call` 工具不在列表中 / 404 | 视图未挂载 | 执行下方「挂载视图」→ 自然引导用户继续对话 → **结束本轮**（下一轮生效） |
| `baiying_call` 超时 | 后端未响应 | 等 30s 后重试一次 |
| `baiying_call` 返回权限错误 | 视图未授权 | 执行下方「挂载视图」→ 结束本轮等待生效 |
| Python import 失败 | 环境未搭建 | 按 [Python 环境搭建](./references/python-env.md) 执行 |
| 脚本执行报错 | 环境变量缺失 | 检查 `BEYOND_TOKEN` `USER_CODE` `BE_DOMAINNAME` |

### 检查视图挂载状态

```bash
# 1. 提取 Agent 的 resource_id（从编码中的数字后缀，如 agent-10014603 → 10014603）
# 2. 查询全部已挂载资源（keyword 按中文名称过滤，可选）
/tmp/ont_env/bin/python scripts/ontology/structured/list_mounted_resources.py \
  '{"resource_id": <Agent的resource_id>}'

# 3. 在返回的 data 数组中查找 resourceCode == "scene_crm_comprehensive_analysis"
#    存在 → 已挂载   不存在 → 执行挂载
```

### 挂载视图

```bash
/tmp/ont_env/bin/python scripts/ontology/structured/mount_resource.py \
  '{"agent_id": <Agent 编码里的数字后缀>, "resource_code": "scene_crm_comprehensive_analysis"}'
```

> `list_resources.py` 只返回个人创建的结构化本体对象，**不能**用于校验平台级视图是否挂载。

### 脚本路径速查

演示 4/5/6 涉及以下脚本（相对于 skill 根目录，通过 `/tmp/ont_env/bin/python` 执行）：

| 脚本 | 用途 |
|------|------|
| `scripts/ontology/structured/list_mounted_resources.py` | 查询 Agent 已挂载的资源 |
| `scripts/ontology/structured/list_resources.py` | 查询个人创建的结构化对象/视图（不含平台级视图） |
| `scripts/ontology/structured/create_object.py` | 创建结构化对象（collect → submit） |
| `scripts/ontology/structured/create_view.py` | 创建本体视图 |
| `scripts/ontology/structured/delete_object.py` | 删除结构化对象 |
| `scripts/ontology/structured/delete_view.py` | 删除本体视图 |
| `scripts/ontology/structured/mount_resource.py` | 挂载视图到当前 Agent |
| `scripts/ontology/structured/list_term_types.py` | 查询可绑定的术语类型 |
| `scripts/ontology/structured/get_term_type_values.py` | 查询术语类型的值列表 |
| `scripts/ontology/unstructured/list_resources.py` | 查询非结构化对象列表 |
| `scripts/ontology/unstructured/list_knowledge_bases.py` | 查询可用知识库（获取 kb_id） |
| `scripts/ontology/unstructured/list_kb_directories.py` | 查询知识库目录 |
| `scripts/ontology/unstructured/create_object.py` | 创建非结构化对象（collect → submit） |
| `scripts/ontology/unstructured/delete_object.py` | 删除非结构化对象 |
| `scripts/ontology/unstructured/mount_resource.py` | 挂载非结构化对象到 Agent |
| `scripts/weekly-report/generate_weekly_report.py` | 生成模拟周报 |

---

## 参考文档

- [歧义处理指南](./references/ambiguity-guide.md) — 五种歧义类型的处理策略与话术模板
- [数据操作指南](./references/data-operations.md) — 周报格式、字段映射、校验规则、任务创建
- [本体对象定义](./references/ontology-objects.md) — 对象字段定义、Mock 数据、脚本调用规范
- [演示场景指南](./references/demo-scenarios.md) — 产品理念话术、FAQ 策略、10min/30min 时间表
- [Python 环境搭建](./references/python-env.md) — 环境首次搭建、环境变量、脚本路径约定

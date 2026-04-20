# dataCloud(数据agent)设计方案

## 1.背景

本方案是《复杂问题方案.md》迭代优化版本。



## 2.设计思想

本框架的设计可分为三个层次：**使用前**完成本体治理（前置依赖）；**运行时**在 agent 层贪心——在工具调用前尽可能多地识别任务、抽取参数、消除歧义；**降级时**在工具层渐进——从简单到复杂逐级兜底。

### 2.1 前置依赖

本框架运行依赖以下本体治理工作，需在正式使用前完成。

1. **术语治理**：梳理字典术语、列表术语及已知同义词，供歧义识别阶段做规则匹配。

2. **本体治理**：将 API 或数据库表建设为本体对象/本体视图。本体属性需绑定字典术语或列表术语，并细分为维度、度量两大类型（详见 §2.2.3）。

### 2.2 分类思想

本框架对数据读取、任务复杂度、本体属性进行了标准化分类，框架运行逻辑基于此分类体系展开。

**1、数据读取任务分类**：数据读取分为查询和统计两类，分别对应 `query_*`、`compute_*` 两类工具。

**2、任务复杂度分类**：分为标准任务和定制任务。定制任务通过 `complex_*` 参数识别，当前实现了"查询条件跨对象"一种类型，后续可扩展更多类型。

**3、本体属性分类**：对象属性分为维度（DIMENSION）和度量（MEASURE）两大类，每类细分若干子类，不同子类在分组、条件过滤、统计函数上有不同规则约束。RANGE 分组函数格式：`RANGE(字段, 开始值, 结束值, '标签')`。

| 属性类型 | 属性类型编码 | 属性子类 | 属性子类编码    | 分组规则                                                     | 条件规则                                                     | 统计函数规则                                                 | 使用示例                                                     | 备注                                       |
| -------- | ------------ | -------- | --------------- | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------ |
| 维度     | DIMENSION    | ID       | id              | 仅支持按自身分组                                             | 1. 适用场景：WHERE 条件、CASE WHEN 条件<br />2. 支持函数：IN、= | ---                                                          | GROUP BY 企业ID<br />WHERE 企业ID IN ('001', '002')          | 外键、英文编码枚举                         |
| 维度     | DIMENSION    | 名称     | name            | 仅支持按自身分组                                             | 1. 适用场景：WHERE 条件、CASE WHEN 条件<br />2. 支持函数：IN、LIKE、= | ---                                                          | GROUP BY 企业名称<br />WHERE 企业名称 LIKE '%科技%'          | 中文字符串枚举                             |
| 维度     | DIMENSION    | 时间     | datetime        | 支持时间粒度函数：<br />DATE()、MONTH()、YEAR()、QUARTER()   | 1. 适用场景：WHERE 条件、CASE WHEN 条件<br />2. 支持函数：IN、=、<=、>=、<、>、BETWEEN | ---                                                          | GROUP BY MONTH(创建时间)<br />WHERE 创建时间 >= '2026-01-01' |                                            |
| 维度     | DIMENSION    | 账期     | period          | 支持时间粒度函数：<br />DATE()、MONTH()、YEAR()、QUARTER()   | 1. 适用场景：WHERE 条件、CASE WHEN 条件<br />2. 支持函数：IN、=、<=、>=、<、>、BETWEEN | ---                                                          | GROUP BY MONTH(账期)<br />WHERE 账期 = '2026-03'             |                                            |
| 维度     | DIMENSION    | 数值     | numeric         | ---                                                          | 1. 适用场景：WHERE 条件、CASE WHEN 条件<br />2. 支持函数：IN、=、<=、>=、<、> | ---                                                          | 仅用于过滤条件<br />CASE WHEN 年龄 > 组织平均年龄 then 1 else 0 | 粗粒度下放用于比较                         |
| 维度     | DIMENSION    | 描述     | description     | ---                                                          | 1. 适用场景：WHERE 条件、CASE WHEN 条件<br />2. 支持函数：LIKE | ---                                                          | WHERE 产品描述 LIKE '%美食%'                                 |                                            |
| 维度     | DIMENSION    | 虚拟标签 | virtual_tag     | 仅支持按自身分组                                             | 1. 适用场景：CASE WHEN 条件<br />2. 支持函数：IN、=          | ---                                                          | CASE WHEN 身高 > 185 and 月收入 > 100000 and 颜值 > 95 then 1 else 0<br /> GROUP BY 高富帅 | 放在本体对象的计算属性                     |
| 度量     | MEASURE      | 主键     | primary_key     | 仅支持按自身分组                                             | 1. 适用场景：WHERE 条件、CASE WHEN 条件<br />2. 支持函数：=、IN | COUNT()                                                      | COUNT(企业ID)                                                |                                            |
| 度量     | MEASURE      | 普通数值 | raw_number      | 支持范围分组：<br />RANGE(字段, 开始值, 结束值, '标签')<br />示例：RANGE(年龄, 0, 6, '婴儿') | 1. 适用场景：WHERE 条件、CASE WHEN 条件<br />2. 支持函数：IN、=、<=、>=、<、> | SUM()、AVG()、MAX()、MIN()、TOPN()、MEDIAN()                 | GROUP BY RANGE(年龄, 0, 18, '未成年')<br />SUM(收入)         |                                            |
| 度量     | MEASURE      | 普通指标 | basic_metric    | 支持范围分组：<br />RANGE(字段, 开始值, 结束值, '标签')<br />示例：RANGE(年营收, 0, 1000000, '小微企业') | 1. 适用场景：WHERE 条件、CASE WHEN 条件<br />2. 支持函数：IN、=、<=、>=、<、> | SUM()、AVG()、MAX()、MIN()、TOPN()、MEDIAN()                 | GROUP BY RANGE(年营收, 0, 1000000, '小微企业')<br />SUM(年营收) | 预计算的聚合指标，如年营收、总销售额       |
| 度量     | MEASURE      | 拍照指标 | snapshot_metric | 支持范围分组：<br />RANGE(字段, 开始值, 结束值, '标签')<br />示例：RANGE(期末余额, 0, 10000000, '小规模') | 1. 适用场景：WHERE 条件、CASE WHEN 条件<br />2. 支持函数：IN、=、<=、>=、<、> | MAX()、MIN()、TOPN()、MEDIAN()；<br />SUM() 跨账期不可加（时点值加总无业务意义），其他维度可加 | GROUP BY RANGE(期末余额, 0, 10000000, '小规模')<br />MAX(期末余额) | 时点快照值，如期末余额、月末库存           |
| 度量     | MEASURE      | 派生指标 | derived_metric  | 支持范围分组：<br />RANGE(字段, 开始值, 结束值, '标签')<br />示例：RANGE(毛利率, 0, 0.3, '低利润率') | 1. 适用场景：WHERE 条件、CASE WHEN 条件<br />2. 支持函数：IN、=、<=、>=、<、> | ---（比率类，不可二次聚合）                                  | GROUP BY RANGE(毛利率, 0, 0.3, '低利润率')<br />WHERE 毛利率 >= 0.5 | 比率类，不可二次计算，仅可比较和展示       |
| 度量     | MEASURE      | 指标公式 | formula_metric  | 支持范围分组：<br />RANGE(字段, 开始值, 结束值, '标签')<br />示例：RANGE(转化率, 0, 0.5, '低转化') | 1. 适用场景：CASE WHEN 条件<br />2. 支持函数：IN、=、<=、>=、<、> | SUM()、AVG()、MAX()、MIN()、TOPN()、MEDIAN()                 | CASE WHEN (收入 - 成本) / 收入 > 0.5 THEN '高毛利' ELSE '低毛利'<br />SUM(收入 - 成本) | 放在本体对象的计算属性，虚拟的，要实时计算 |

---

### 2.3 贪心思想

利用 agent 的 ReAct & function call 机制，在工具调用**前**尽可能完成任务识别和参数抽取，减少工具调用轮次。贪心阶段的产出直接决定渐进阶段（§2.4）走哪条路。

| 任务                   | 决策内容                                                       | 输出 / 后续动作                                              |
| ---------------------- | -------------------------------------------------------------- | ------------------------------------------------------------ |
| 选工具（本体）         | 根据工具描述中的字段能力表，确定目标对象/视图                  | 输出 `{code}`，确定工具名前缀                                |
| 选工具（任务分类）     | 确定意图：查明细 or 做统计                                     | 输出工具名：`query_{code}` 或 `compute_{code}`               |
| 参数抽取（标准参数）   | 从自然语言抽取结构化参数（select、filters、order_by 等）       | 输出 tool_params，进入 §2.4 渐进流程                        |
| 参数抽取（字段映射）   | LLM 对照工具描述中的字段能力表（字段编码 + 中文名）做直接匹配：能命中则取表中编码或名称；**无法直接推理出对应字段时，原词写入参数，禁止猜测替换为相近已有字段** | 命中：field 写 field_code 或中文名；未命中：field 写用户原词（如 `"贡献率"`），映射与歧义处理交由 §2.4 渐进阶段 |
| 参数抽取（复杂子条件识别）| 识别**过滤值无法在填参时确定为字面常量**的条件（如相对排名、跨对象子查询、与均值比较等），将该条件的完整自然语言原文写入 `complex_conditions`；其余可字面化的过滤条件仍正常填入 `filters` | 输出 complex_conditions → §2.4 任务复杂渐进走 text2SQL 路径 |

**字段映射原则**：LLM 在填写 `select` / `filters.field` / `order_by.field` 时，直接对照工具描述里的字段能力表（由 `build_query_description` / `build_compute_description` 生成，含 `field_code` 和中文名两列）进行匹配。**能直接命中则取表中的编码或名称；无法直接推理出对应字段时，保留用户原词写入，禁止猜测性地替换为已有字段**。字段能力表同时也嵌入在 schema 的 `x-dc-field-catalog` 扩展字段中供工具层做后续解析。

> **示例**：用户说"查询物理网格数据，包含网格编码、网格名称、贡献率三个字段，条件是贡献率大于100"。字段能力表中有"网格编码"和"网格名称"，直接命中；"贡献率"不在表中，**不得**强行替换为已有字段"营收值"，直接原词写入：
>
> ```json
> {
>   "query": "查询物理网格数据，包含网格编码、网格名称、贡献率三个字段，条件是贡献率大于100",
>   "select": ["网格编码", "网格名称", "贡献率"],
>   "filters": [
>     { "field": "贡献率", "op": "gt", "value": 100 }
>   ],
>   "limit": 10
> }
> ```
>
> 渐进阶段（§2.4）再对"贡献率"做规则修正或触发 interrupt 追问用户。

**复杂子条件识别原则**：`complex_conditions` 只收**过滤值**在填参时无法确定为字面常量的那部分条件，包括：①相对排名（"后30%"、"前N名"）；②跨对象子查询（如"亩产效益后30%的地块"作为过滤范围）；③动态比较值（"高于行业平均"）。其余可字面化的条件（包括字段名未命中但值可字面化的情况）仍按正常参数填写。`complex_conditions` 每一项只写**无法字面化的那个条件片段**，由后端路由到 text2SQL 处理。

> **示例**：用户说"找出亩产效益后30%的地块，查询这些地块上的中、低效能的企业清单"。工具选 `query_enterprise_view`，"亩产效益后30%的地块"是跨对象子查询、值无法字面化，只将该片段写入 `complex_conditions`；效能等级（中、低）若字段能命中则正常填 `filters`：
>
> ```json
> {
>   "query": "找出亩产效益后30%的地块，查询这些地块上的中、低效能的企业清单",
>   "complex_conditions": [
>     "亩产效益后30%的地块"
>   ],
>   "select": [],
>   "filters": [
>     { "field": "效能等级", "op": "in", "value": ["中", "低"] }
>   ],
>   "limit": 100
> }
> ```
>
> `complex_conditions` 非空时系统自动路由到 `data_query_{code}`（text2SQL 路径）。



### 2.4 渐进思想

贪心阶段识别出任务类型和参数后，渐进思想决定工具层如何降级执行——优先走简单路径，能自动处理则自动，不能处理则逐级升级。

**1、任务复杂渐进**：优先引导 LLM 使用 `query_{code}` / `compute_{code}` 标准工具，规则转 DSL；若包含 `complex_conditions` 参数，则转路由到 `data_query_{code}`，走 text2SQL。

**2、意图澄清渐进**（数据查询场景）：

- 先通过规则进行歧义意图判断（标准术语 + 术语同义词）。
- 能自动修正尽量自动修正：
  - 能局部修正则局部修正（如 select 有歧义只修正 select，filters 有歧义只修正 filters）。
  - 无法局部修正则整体修正（重新调整 select、from、where）。
- 无法自动修正时，列出可能选项，触发 interrupt 让用户确认后继续执行。

## 3.建设目标

1、性能目标：

1）首字节响应 及平均响应：首字节1秒，平均每秒20个文字或字母输出。

2）完成时间：简单任务(text2Dsl)：5-15秒完成任务处理，复杂任务(text2Sql)：15-3分钟完成处理。

2、准确率目标：基于XXX评测集准确率达95%。





## 4.现状差距分析

### 4.1贪心阶段现状分析

分析涉及三个文件：
- **工具描述生成**：`packages/datacloud-data/src/datacloud_data_sdk/virtual_action/generator.py`
- **ReAct 提示词**：`packages/datacloud-analysis/src/datacloud_analysis/i18n/prompts.py`
- **工具参数 schema**：同 `generator.py` 中 `build_query_schema` / `build_compute_schema`

---

#### 4.1.1 工具描述生成（generator.py）

**现状**：`build_query_description` / `build_compute_description` 生成的描述包含：对象说明 + "何时使用" + 字段能力表（8列）+ "常见错误"；schema 中 `select` 带 `x-dc-field-catalog`（name+code 清单），`order_by.field` 有原词透传指令。

| 贪心任务 | 描述是否支持 | 说明 |
| --- | --- | --- |
| 选工具（本体） | ✅ 支持 | 字段能力表覆盖了编码+中文名，LLM 可据此识别目标对象 |
| 选工具（任务分类） | ⚠️ 弱 | "何时使用"有 query vs compute 的说明，但没有明确决策规则 |
| 参数抽取（标准参数） | ✅ 支持 | select / filters / order_by 的 schema 完整 |
| 参数抽取（字段映射）| ⚠️ 部分 | `select` 和 `order_by` 有原词透传指令；**`filters.field` 描述仅说"系统自动识别映射"，缺少"找不到时填原词"的指令** |
| 参数抽取（复杂子条件识别）| ❌ 有冲突 | `complex_conditions` 触发条件 2 写的是"字段名找不到精确对应 → 写入 complex_conditions"，与设计不符：字段未命中应原词透传到标准参数，`complex_conditions` 只收值无法字面化的条件 |

**具体差距：**

1. **`complex_conditions` 触发条件 2 与设计冲突**（`build_query_schema` / `build_compute_schema` 的 `complex_conditions.description`）：
   ```
   # 当前描述（有误）：
   "2. 查询/排序/返回所涉及的字段名在当前对象字段列表中找不到精确对应（如'贡献率'、'地块'等非标准词），需系统做语义推断"
   ```
   设计要求：字段名未命中 → 原词写入 `select`/`filters`/`order_by`；`complex_conditions` 只收**值无法字面化**的条件（相对排名、跨对象子查询、动态比较值）。

2. **`filters.field` 缺少原词透传指令**：各字段的 `_filter_item_schema` 只写了 "字段中文名或字段编码，系统自动识别映射"，未说明"找不到时直接填用户原词"，与 `select` 和 `order_by` 的指令不一致。

3. **"常见错误"中"field 填了不存在的字段名（系统无法映射时会报错）"与设计矛盾**：设计要求未命中字段原词透传，工具层负责语义解析，不应该报错拒绝。该提示会干扰 LLM，使其倾向于猜测替换而非透传原词。

4. **字段能力表 8 列中有 3 列与 schema 冗余**：可过滤（filter_ops）、可分组（group_ops）、可聚合（agg_ops）的具体操作符已经在 schema 的 `filters.oneOf` / `dimensions.oneOf` / `metrics.oneOf` 中逐字段声明，description 里再列一遍对 LLM 无增量信息，仅增加 token 消耗（详见 §4.2）。

---

#### 4.1.2 工具参数 Schema（build_query_schema / build_compute_schema）

**现状**：schema 通过 `oneOf` 逐字段声明合法参数，核心字段包括：`query`（必填自然语言）、`select`（带 `x-dc-field-catalog`）、`filters`（filterable 字段的 oneOf）、`order_by`、`complex_conditions`、`dimensions` / `metrics`（compute 专属）。

| 贪心任务 | Schema 是否支持 | 说明 |
| --- | --- | --- |
| 参数抽取（字段映射）— select | ✅ 支持 | `select` 带 `x-dc-field-catalog`（name+code 清单）且有原词透传指令 |
| 参数抽取（字段映射）— order_by | ✅ 支持 | `order_by.field` 有"找不到时填原词"指令 |
| 参数抽取（字段映射）— filters | ❌ 有缺口 | `filters` 的 oneOf 仅列出可过滤字段；**若用户词未命中任何一项，LLM 无法找到匹配的 oneOf，行为未定义（可能拒填或猜测替换）**；且 `filters.field` 描述无原词透传指令 |
| 参数抽取（复杂子条件识别） | ❌ 有冲突 | `complex_conditions.description` 触发条件 2（字段名未命中 → complex_conditions）与设计不符，同 §4.1.1 |
| 选工具（任务分类）— compute | ⚠️ 弱 | `dimensions` / `metrics` 的 oneOf 结构隐含了字段的角色分类，但无明确"何时选 compute"的决策规则 |

**具体差距：**

1. **`filters` oneOf 仅覆盖可过滤字段，字段未命中时缺少兜底**：当用户说"贡献率大于100"而"贡献率"不在 filterable 列表里，`filters.items.oneOf` 中没有任何匹配项，schema 层没有原词透传的兜底路径。需要补充一个 catch-all 条目或在 `filters.description` 中显式说明"字段未命中时直接填用户原词"。

2. **`compute` schema 的 `metrics` 要求 `required: ["field", "agg", "as"]`，但字段未命中时 `field` 填原词是否合法未说明**：与 `select` 场景类似，但 compute 场景下字段原词透传的处理路径更不清晰。

3. **schema 整体体积大**：`filters.oneOf` 按字段逐一展开（每个字段一个完整 schema 对象），字段数多时 schema JSON 非常长，增加 LLM 上下文消耗，且与 description 中字段能力表的 filter_ops 列重复。

---

#### 4.1.4 ReAct 提示词（prompts.py）

**现状**：`get_execution_prompt` 包含执行规则、工具命名规则、compute 参数规则、查询参数规则、complex_conditions 规则、返回结果规则等。

| 贪心任务 | 提示词是否覆盖 | 说明 |
| --- | --- | --- |
| 选工具（本体） | ❌ 缺失 | 没有引导 LLM 先对照字段能力表识别目标对象/视图，再确定工具名前缀 |
| 选工具（任务分类） | ❌ 缺失 | 没有说"先判断意图是查明细还是做统计，再选 `query_*` 或 `compute_*`" |
| 参数抽取（标准参数） | ✅ 有 | query、select、filters 等参数规则有覆盖 |
| 参数抽取（字段映射） | ⚠️ 有冲突 | "字段名不存在时必须透传原词"规则正确，但紧随其后写"同时将该字段涉及的完整条件写入 complex_conditions"——制造了双写冲突：字段未命中时，到底只透传原词到标准参数，还是要同时写 complex_conditions？ |
| 参数抽取（复杂子条件识别）| ❌ 有冲突 | `complex_conditions` 触发条件 2（字段名找不到 → complex_conditions）与设计不符，同上 |

**具体差距：**

1. **贪心"选工具"两个步骤完全缺失**：提示词没有明确的工具选择引导序——先从字段能力表识别目标对象，再判断 query vs compute。LLM 完全依赖工具描述自行推断，容易在多本体场景下选错工具。

2. **字段未命中规则与 complex_conditions 规则冲突**（`_build_exec_zh` 第 149–158 行）：
   
   ```
   # 第 152 行（有误）：
   "同时将该字段涉及的完整条件写入 complex_conditions"
   # 第 156–157 行（有误）：
   "2. 查询/排序/返回所涉及的字段名在工具字段列表中找不到精确对应...需要系统做语义推断"
   ```
   设计要求：字段未命中 → 只透传原词到标准参数；`complex_conditions` 只收**值无法字面化**的子条件。两条规则要严格分开，不能混用。
   
3. **"查询工具参数规则"中的关键词提取逻辑是历史遗留**（第 134–142 行）：关于"关键词只能是名词短语""不能是停用词副词"的描述来自早期全文检索范式，与当前贪心参数抽取策略（直接填字段名/字段编码）不吻合，会干扰 LLM 的参数填写行为。

---



#### 4.1.4 字段能力表列精简分析

**现状**：`_field_table_row` 生成 8 列：`字段编码 | 中文名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明`。

| 列 | 作用 | 是否与 schema 冗余 | 建议 |
| --- | --- | --- | --- |
| 字段编码 | 字段映射的核心标识 | 否 | **保留** |
| 中文名 | 字段映射的核心标识 | 否 | **保留** |
| 角色（dimension/measure） | LLM 据此判断 query vs compute，是任务分类的关键信号 | 否 | **保留** |
| 类型（analytic_kind） | 细化角色语义（如 snapshot_metric 跨账期不可 SUM），有一定价值 | 否 | **保留**（可考虑合并到特殊说明列） |
| 可过滤（filter_ops） | 列出合法 filter 操作符 | **是**，`filters.oneOf` 每字段已声明合法 ops | 删除 |
| 可分组（group_ops） | 列出合法 group 操作符 | **是**，`dimensions.oneOf` 每字段已声明合法 ops | 删除 |
| 可聚合（agg_ops） | 列出合法聚合函数 | **是**，`metrics.oneOf` 每字段已声明合法 agg | 删除 |
| 特殊说明（必须过滤） | 强制过滤字段（如账期），漏填代价高 | 否 | **保留** |

**结论**：可安全删除"可过滤/可分组/可聚合"3列，每行 token 减少约 40–50%，保留"字段编码 | 中文名 | 角色 | 类型 | 特殊说明"5列。若进一步精简，可将"类型"合并到"特殊说明"中（仅对 snapshot_metric 等有特殊限制的字段写注释），降到 4 列。

> **注意**：删除 description 中的 3 列后，LLM 判断某字段是否可过滤/分组/聚合的信息来源完全依赖 schema 的 oneOf 结构。这要求 schema 的 oneOf 必须准确且有良好的兜底逻辑（即补全 §4.1.2 中字段未命中时的兜底条目），否则信息断层。

#### 4.1.5 综合结论

| 差距项                                                       | 涉及文件                        | 优先级 |
| ------------------------------------------------------------ | ------------------------------- | ------ |
| `complex_conditions` 触发条件 2 与设计冲突（字段未命中不应进 complex_conditions） | generator.py schema、prompts.py | 高     |
| 字段未命中"透传原词"规则与 complex_conditions 双写冲突（prompts.py 第 152 行） | prompts.py                      | 高     |
| `filters` oneOf 无兜底：字段未命中时 LLM 行为未定义          | generator.py schema             | 高     |
| `filters.field` 缺少原词透传指令（description 和 schema 均缺） | generator.py                    | 中     |
| 贪心"选工具（本体+任务分类）"步骤在提示词中完全缺失          | prompts.py                      | 中     |
| "常见错误"中"字段不存在会报错"误导 LLM 不敢透传原词          | generator.py description        | 中     |
| schema filters.oneOf 与 description 字段能力表 filter_ops 列重复，双倍 token 消耗 | generator.py                    | 低     |
| 历史遗留的关键词提取逻辑干扰参数抽取                         | prompts.py                      | 低     |

---





## 5.详细设计

### 5.1 贪心阶段优化

基于 §4.1 差距分析，优化分为两个文件的改动：`generator.py`（工具描述 + schema）和 `prompts.py`（ReAct 提示词）。

---

#### 5.1.1 【高】修复 complex_conditions 触发条件 2 冲突

**问题**：`complex_conditions` 触发条件 2（"字段名找不到 → 写入 complex_conditions"）与"字段映射原词透传"规则冲突，两者语义重叠，导致 LLM 不知道字段未命中时该写 filters 还是写 complex_conditions。

**正确语义**：`complex_conditions` 只收**过滤值无法字面化**的条件；字段名未命中时只原词透传到标准参数，不进 complex_conditions。

**改动文件 1**：`generator.py` → `build_query_schema` 和 `build_compute_schema` 中 `complex_conditions.description`

```python
# 改前
"complex_conditions": {
    "description": (
        "溢出过滤区：满足以下任一条件时，必须将该条件用自然语言写入此列表：\n"
        "1. 过滤条件的值无法在填参时确定为字面常量（如'后30%'、'高于行业平均'）；\n"
        "2. 查询/排序/返回所涉及的字段名在当前对象字段列表中找不到精确对应"
        "（如'贡献率'、'地块'等非标准词），需系统做语义推断。\n"
        ...
    )
}

# 改后
"complex_conditions": {
    "description": (
        "溢出过滤区：仅当**过滤值在填参时无法确定为字面常量**时，将该条件片段用自然语言写入此列表。\n"
        "触发场景：\n"
        "1. 相对排名（如'后30%'、'前N名'）；\n"
        "2. 跨对象子查询（如'亩产效益后30%的地块'作为过滤范围）；\n"
        "3. 动态比较值（如'高于行业平均'）。\n"
        "⚠️ 字段名在字段列表中找不到时，不写入此列表——直接在 select/filters/order_by 中填原词。\n"
        "写入内容：只写**无法字面化的那个条件片段**，不写整句查询。\n"
        "例：'亩产效益后30%的地块'（正确）；'查询这些地块上的中低效能企业'（错误，整句不写）。\n"
        "此列表非空时系统自动路由到全能查询路径（data_query），无需手动调用。"
    )
}
```

**改动文件 2**：`prompts.py` → `_build_exec_zh` 中 `complex_conditions` 规则块

```python
# 改前（第 153–160 行）
"- **complex_conditions（溢出过滤区）**：\n",
"  满足以下任一条件时，必须将该条件用自然语言写入此列表：\n",
"  1. 过滤条件的值在填参时无法确定为字面常量（如'后30%'、'高于平均'、'排名前10名'）；\n",
"  2. 查询/排序/返回所涉及的字段名在工具字段列表中找不到精确对应（如'贡献率'、'地块'等\n",
"     非标准词），需要系统做语义推断。\n",

# 改后
"- **complex_conditions（溢出过滤区）**：\n",
"  仅当**过滤值无法确定为字面常量**时，将该条件片段写入此列表。\n",
"  触发场景：①相对排名（'后30%'、'前N名'）；②跨对象子查询；③动态比较值（'高于行业平均'）。\n",
"  ⚠️ 字段名找不到时**不写此列表**，直接在 filters/select/order_by 中填原词；\n",
"     complex_conditions 和字段原词透传是两个独立规则，不能混用。\n",
"  写入内容：只写无法字面化的条件片段（如'亩产效益后30%的地块'），不写整句查询。\n",
```

---

#### 5.1.2 【高】修复 filters 字段未命中双写冲突

**问题**：`prompts.py` 第 152 行在说明"字段名透传原词"后紧接"同时将该字段涉及的完整条件写入 complex_conditions"，与 §5.1.1 修复后的规则冲突。

**改动文件**：`prompts.py` → `_build_exec_zh` 字段映射规则块

```python
# 改前（第 149–152 行）
"  ⚠️ **字段名不存在时必须透传原词**：若某个词（如'贡献率'、'地块'）在工具的字段列表中\n",
"  找不到精确对应，禁止猜测替换为相近字段名；必须将用户的原始词直接填入对应参数\n",
"  （如 select: ['贡献率']、order_by: [{'field': '贡献率', 'direction': 'asc'}]），\n",
"  系统后端会做语义解析。同时将该字段涉及的完整条件写入 complex_conditions。\n",

# 改后
"  ⚠️ **字段名不存在时必须透传原词**：若某个词（如'贡献率'）在工具字段列表中\n",
"  找不到精确对应，禁止猜测替换为相近字段名；直接将用户原始词填入对应参数\n",
"  （select: ['贡献率']、filters: [{'field': '贡献率', 'op': 'gt', 'value': 100}]、\n",
"   order_by: [{'field': '贡献率', 'direction': 'asc'}]），系统后端负责语义解析。\n",
"  字段名透传与 complex_conditions 是独立规则：透传原词不触发 complex_conditions。\n",
```

---

#### 5.1.3 【高】为 filters oneOf 添加 catch-all 兜底条目

**问题**：`filters.items.oneOf` 只列出 filterable 字段，用户词未命中时 LLM 无任何 schema 匹配项，行为未定义。

**改动文件**：`generator.py` → `_build_filters_schema`

```python
# 在 _build_filters_schema 末尾，items.oneOf 追加一个 catch-all 条目

_FILTER_CATCHALL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "【兜底条目】当字段名在当前对象字段列表中找不到精确对应时使用。"
        "直接将用户原始词填入 field，系统后端负责语义解析；禁止猜测替换为相近字段名。"
    ),
    "properties": {
        "field": {
            "type": "string",
            "description": "用户原始字段词（如'贡献率'），找不到精确对应时直接填原词",
        },
        "op": {
            "type": "string",
            "enum": ["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in",
                     "like", "is_null", "is_not_null", "between"],
            "description": "过滤操作符",
        },
        "value": {
            "description": "过滤值（字面常量）；is_null/is_not_null 不需要",
            "oneOf": [
                {"type": "string"},
                {"type": "number"},
                {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "number"}]}},
            ],
        },
    },
    "required": ["field", "op"],
}

def _build_filters_schema(fields: list[Any]) -> dict[str, Any]:
    filterable = [f for f in fields if getattr(f, "filter_ops", [])]
    if not filterable:
        return {"type": "array", "items": {"type": "object"}, "description": "过滤条件列表"}
    return {
        "type": "array",
        "description": "过滤条件列表，field 填字段中文名或字段编码；字段名找不到时直接填用户原词",
        "items": {
            "oneOf": [_filter_item_schema(f) for f in filterable] + [_FILTER_CATCHALL_SCHEMA]  # ← 追加兜底
        },
        "x-dc-filterable-fields": [...],  # 不变
    }
```

同时修改 `_build_filters_schema` 的顶层 `description`，明确说明兜底行为：

```python
# 改前
"description": "过滤条件列表，field 填字段中文名或字段编码",

# 改后
"description": (
    "过滤条件列表，field 填字段中文名或字段编码；"
    "字段名在列表中找不到精确对应时，直接填用户原词（如'贡献率'），系统后端负责语义解析。"
),
```

---

#### 5.1.4 【中】补充 filters.field 原词透传指令

**问题**：`_filter_item_schema` 的 `field.description` 只说"系统自动识别映射"，缺少"找不到时填原词"的指令，与 `select`、`order_by` 不一致。

**改动文件**：`generator.py` → `_filter_item_schema`

```python
# 改前
"field": {
    "type": "string",
    "description": (
        f"字段中文名（如 '{field_name}'）或字段编码（如 '{field_code}'），系统自动识别映射。"
    ),
},

# 改后
"field": {
    "type": "string",
    "description": (
        f"字段中文名（如 '{field_name}'）或字段编码（如 '{field_code}'），系统自动识别映射；"
        "若字段名在当前对象中找不到精确对应，直接填用户原始词，禁止猜测替换为相近字段名。"
    ),
},
```

---

#### 5.1.5 【中】新增：贪心选工具引导（prompts.py）

**问题**：提示词完全没有引导 LLM 先选对象再选工具类型的步骤，多本体场景易选错。

**改动文件**：`prompts.py` → `_build_exec_zh`，在"查询工具命名规则"之后新增"工具选择引导"块：

```python
# 在 _get_query_tool_hint_zh() 返回内容末尾（或作为独立 part 追加）新增：
"## 工具选择引导（贪心策略）\n",
"在调用任何查询工具前，先完成以下两步判断：\n",
"1. **选对象（本体）**：对照各工具描述中的字段能力表（字段编码+中文名），"
"   确定用户问题所指向的对象/视图，得到工具名前缀（如 `grid_physical`）。\n",
"2. **选任务类型**：\n",
"   - 用户要查看具体记录列表（明细）→ 选 `query_{对象编码}`\n",
"   - 用户要做分组统计、汇总指标 → 选 `compute_{对象编码}`\n",
"   - 如果同一问题涉及明细和统计，优先拆成两次调用。\n",
"确定工具后，再填写 select / filters / dimensions / metrics 等参数。\n",
```

---

#### 5.1.6 【中】修正"常见错误"误导性描述（generator.py）

**问题**："field 填了不存在的字段名（系统无法映射时会报错）"会让 LLM 不敢填原词，倾向于猜测替换。

**改动文件**：`generator.py` → `build_query_description` 和 `build_compute_description` 的"常见错误"部分

```python
# 改前
lines.append("- field 填了不存在的字段名（系统无法映射时会报错）")

# 改后
lines.append(
    "- 字段名找不到时猜测替换为相近字段（如把'贡献率'改成'营收值'）——"
    "应直接填用户原词，系统后端负责语义解析"
)
```

---

#### 5.1.7 【低】精简字段能力表冗余列（generator.py）

**问题**：可过滤/可分组/可聚合 3 列与 schema oneOf 完全重复，每行多消耗约 40% token。

**改动文件**：`generator.py` → `_field_table_row` 和表头

```python
# 改前
def _field_table_row(f: Any) -> str:
    ...
    filter_ops = "/".join(getattr(f, "filter_ops", []) or []) or "-"
    group_ops = "/".join(getattr(f, "group_ops", []) or []) or "-"
    agg_ops = "/".join(getattr(f, "aggregate_ops", []) or []) or "-"
    req = "必须过滤" if getattr(f, "required_filter_group", None) else ""
    return f"| {fc} | {fn} | {role} | {kind} | {filter_ops} | {group_ops} | {agg_ops} | {req} |"

# 改后（删除 filter_ops / group_ops / agg_ops 三列）
def _field_table_row(f: Any) -> str:
    ...
    req = "必须过滤" if getattr(f, "required_filter_group", None) else ""
    kind_note = kind if kind in ("snapshot_metric", "derived_metric", "formula_metric") else ""
    return f"| {fc} | {fn} | {role} | {kind_note} | {req} |"

# 对应表头同步修改（build_query_description / build_compute_description）
# 改前
lines.append("| 字段编码 | 中文名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明 |")
lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
# 改后
lines.append("| 字段编码 | 中文名 | 角色 | 类型 | 特殊说明 |")
lines.append("| --- | --- | --- | --- | --- |")
```

> **前置条件**：此改动依赖 §5.1.3（filters oneOf catch-all 兜底）已完成，否则 LLM 失去"该字段可过滤"的 description 侧信息后，面对字段未命中场景缺乏引导。

---

#### 5.1.8 【低】清理历史遗留关键词提取逻辑（prompts.py）

**问题**：`_build_exec_zh` 第 134–142 行的关键词提取描述（"关键词只能是名词短语""不能是停用词"）来自旧检索范式，与当前直接填字段名/编码的贪心策略冲突，干扰 LLM 参数填写。

**改动文件**：`prompts.py` → `_build_exec_zh`

```python
# 删除以下内容（第 134–142 行）：
"- 理解用户提问的主要焦点和具体细节，分析出提问所代表的查询目标、分组条件、过滤条件、排序目标、统计函数中的关键字分别是什么\n",
"- 关键词是命名实体（如组织、地点等）、专业术语以及其他包含查询重要方面的短语\n",
"- 关键词只能是：名词或名词短语；不能是：常见的停用词，副词，表示数值的数量词,表示统计相关的动词\n",
"- 问题的相关术语可以作为关键词的一个重要参考\n",
"- 查询目标：包含指标(可统计的数值型术语)和维度名称(分类属性)，不包含统计相关的动词，如果用户的提问比较口语化请用较为专业的术语来表示\n",
"- 分组条件：主要是离散型维度名称\n",
"- 过滤条件：主要是维度名称下具体维度取值，或指标的数值条件限定\n",
"- 排序目标：可排序的指标或维度名称字段\n",
"- 统计函数：聚合函数，数据计算的相关运算,统计相关的动词\n",
```

---

#### 5.1.9 改动优先级汇总

| 子节 | 改动内容 | 文件 | 优先级 |
| --- | --- | --- | --- |
| 5.1.1 | 修复 complex_conditions 触发条件 2 | generator.py schema、prompts.py | 高 |
| 5.1.2 | 修复字段未命中双写冲突 | prompts.py | 高 |
| 5.1.3 | filters oneOf 添加 catch-all 兜底 | generator.py | 高 |
| 5.1.4 | filters.field 补充原词透传指令 | generator.py | 中 |
| 5.1.5 | 新增贪心选工具引导 | prompts.py | 中 |
| 5.1.6 | 修正"常见错误"误导性描述 | generator.py | 中 |
| 5.1.7 | 精简字段能力表冗余 3 列 | generator.py | 低 |
| 5.1.8 | 清理历史遗留关键词提取逻辑 | prompts.py | 低 |

---

#### 5.1.10 验收用例

> **说明**：以下用例为 LLM 行为验收测试，需在完成对应改动后，向 Agent 发送"用户输入"，检查工具调用参数是否符合"验收标准"。测试前提：已挂载包含字段能力表的 `query_grid_physical`（物理网格对象）和 `query_enterprise_view`（企业视图）两个工具，字段能力表中**包含**"网格编码、网格名称、效能等级"，**不包含**"贡献率、亩产效益"。

---

##### 字段映射类

**TC-01 字段命中 → 使用表中名称，不变形**

| 项 | 内容 |
| --- | --- |
| 验收点 | §5.1.1 / §5.1.4 |
| 用户输入 | "查询物理网格数据，包含网格编码和网格名称" |
| 预期工具 | `query_grid_physical` |
| 预期参数关键字段 | `select: ["网格编码", "网格名称"]` 或对应 field_code；`complex_conditions: []` |
| **失败判定** | select 中字段名被替换为其他名称；或 complex_conditions 非空 |

---

**TC-02 select 字段未命中 → 原词透传，禁止猜测替换**

| 项 | 内容 |
| --- | --- |
| 验收点 | §5.1.1 / §5.1.2 |
| 用户输入 | "查询物理网格数据，包含网格编码、网格名称、贡献率三个字段" |
| 预期工具 | `query_grid_physical` |
| 预期参数关键字段 | `select: ["网格编码", "网格名称", "贡献率"]`；`complex_conditions: []` |
| **失败判定** | "贡献率"被替换为"营收值"等已有字段；或 complex_conditions 包含贡献率相关内容 |

---

**TC-03 filters 字段未命中 → 原词透传到 filters，不进 complex_conditions**

| 项 | 内容 |
| --- | --- |
| 验收点 | §5.1.1 / §5.1.2 / §5.1.3 / §5.1.4 |
| 用户输入 | "查询物理网格数据，条件是贡献率大于100" |
| 预期工具 | `query_grid_physical` |
| 预期参数关键字段 | `filters: [{"field": "贡献率", "op": "gt", "value": 100}]`；`complex_conditions: []` |
| **失败判定** | filters 为空；或 complex_conditions 包含"贡献率"相关内容；或 filters.field 被替换为其他字段名 |

---

**TC-04 order_by 字段未命中 → 原词透传**

| 项 | 内容 |
| --- | --- |
| 验收点 | §5.1.1 / §5.1.2 |
| 用户输入 | "查询物理网格数据，按贡献率降序排列" |
| 预期工具 | `query_grid_physical` |
| 预期参数关键字段 | `order_by: [{"field": "贡献率", "direction": "desc"}]`；`complex_conditions: []` |
| **失败判定** | order_by.field 被替换；或 complex_conditions 包含"贡献率"相关内容 |

---

##### complex_conditions 类

**TC-05 相对排名 → 写入 complex_conditions**

| 项 | 内容 |
| --- | --- |
| 验收点 | §5.1.1 |
| 用户输入 | "查询亩产效益后30%的地块清单" |
| 预期工具 | `query_grid_physical` |
| 预期参数关键字段 | `complex_conditions: ["亩产效益后30%的地块"]`（或语义等价的片段）；不是整句写入 |
| **失败判定** | complex_conditions 为空；或整句"查询亩产效益后30%的地块清单"被整体写入 |

---

**TC-06 动态比较值 → 写入 complex_conditions**

| 项 | 内容 |
| --- | --- |
| 验收点 | §5.1.1 |
| 用户输入 | "查询营收高于行业平均值的企业" |
| 预期工具 | `query_enterprise_view` |
| 预期参数关键字段 | `complex_conditions: ["营收高于行业平均值"]`（或语义等价的片段） |
| **失败判定** | complex_conditions 为空；或该条件被写入 filters（因为"行业平均值"无法字面化） |

---

**TC-07 混合场景：字段未命中（原词透传）+ 值无法字面化（complex_conditions）并存**

| 项 | 内容 |
| --- | --- |
| 验收点 | §5.1.1 / §5.1.2 / §5.1.3 |
| 用户输入 | "找出亩产效益后30%的地块，查询这些地块上的中、低效能的企业清单" |
| 预期工具 | `query_enterprise_view` |
| 预期参数关键字段 | `complex_conditions: ["亩产效益后30%的地块"]`；`filters: [{"field": "效能等级", "op": "in", "value": ["中", "低"]}]` |
| **失败判定** | complex_conditions 包含"效能等级"相关条件；或"效能等级"过滤条件丢失；或 complex_conditions 为整句 |

---

**TC-08 混合场景：字段未命中 + 值无法字面化，两者独立处理**

| 项 | 内容 |
| --- | --- |
| 验收点 | §5.1.1 / §5.1.2 / §5.1.3 |
| 用户输入 | "查询物理网格，贡献率大于100且亩产效益后30%的地块" |
| 预期工具 | `query_grid_physical` |
| 预期参数关键字段 | `filters: [{"field": "贡献率", "op": "gt", "value": 100}]`；`complex_conditions: ["亩产效益后30%的地块"]` |
| **失败判定** | "贡献率大于100"进了 complex_conditions；或两个条件都在 complex_conditions；或 complex_conditions 为空 |

---

##### 工具选择类

**TC-09 明细查询 → 选 query_\***

| 项 | 内容 |
| --- | --- |
| 验收点 | §5.1.5 |
| 用户输入 | "查看物理网格的明细列表，包含网格编码和网格名称" |
| 预期工具 | `query_grid_physical` |
| **失败判定** | 选择了 `compute_grid_physical` |

---

**TC-10 分组统计 → 选 compute_\***

| 项 | 内容 |
| --- | --- |
| 验收点 | §5.1.5 |
| 用户输入 | "统计各网格等级下的网格数量" |
| 预期工具 | `compute_grid_physical` |
| 预期参数关键字段 | `dimensions: [{"field": "效能等级", "group_op": "direct"}]`；`metrics: [{"agg": "count_all", "as": "网格数量"}]` |
| **失败判定** | 选择了 `query_grid_physical`；或未填 dimensions/metrics |

---

**TC-11 多本体场景 → 选对目标对象**

| 项 | 内容 |
| --- | --- |
| 验收点 | §5.1.5 |
| 用户输入 | "查询企业的营收数据" |
| 预期工具 | `query_enterprise_view`（企业视图，而非物理网格工具） |
| **失败判定** | 选择了 `query_grid_physical` 或其他非企业对象的工具 |
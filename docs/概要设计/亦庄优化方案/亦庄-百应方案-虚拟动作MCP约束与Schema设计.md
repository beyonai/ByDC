# 亦庄-百应方案-虚拟动作MCP约束与Schema设计

## 1. 文档目标

本文回答三个问题：

1. 怎么更好地约束和描述 MCP 中每个字段的限制条件。
2. 虚拟动作生成时，描述文档应该怎么组织。
3. MCP `inputSchema` 应该如何设计，既让模型好理解，又能让服务端好校验。

本文是 [虚拟动作改造详细设计](./亦庄-百应方案-虚拟动作改造详细设计.md) 的配套规范，重点面向：

- 虚拟动作生成器
- MCP `tools/list`
- 技能包生成器
- 服务端入参校验器

---

## 2. 结论先行

要把 MCP 字段约束描述清楚，不能只靠一层 `inputSchema`。推荐使用“三层约束模型”：

| 层级 | 作用 | 承载位置 |
| --- | --- | --- |
| 结构层 | 描述字段形状、类型、必填、枚举、数组大小 | 标准 JSON Schema |
| 语义层 | 描述字段能力、操作符限制、术语解析规则、强制过滤规则 | `x-dc-*` 扩展元数据 + description |
| 执行层 | 做跨字段校验、权限校验、账期强制校验、兼容旧协议 | 服务端 `Validator` |

推荐原则：

- 标准 JSON Schema 负责”格式正确”。
- 扩展元数据负责”模型可理解”。
- 服务端校验负责”业务上合法”。

> **关于 x-dc-* 字段兼容性**：当前项目使用官方 MCP SDK（非 FastMCP），SDK 对 inputSchema 不做结构校验，`x-dc-*` 作为 JSON Schema 扩展关键字放在 inputSchema 中是安全的。若后续需要兼容严格 MCP 客户端，可将 `x-dc-*` 迁移到 Tool 的 `annotations` 字段。详见第 13 节。

---

## 3. 为什么只靠 JSON Schema 不够

如果只靠普通 JSON Schema，会遇到以下问题：

| 问题 | 示例 |
| --- | --- |
| 难表达字段级操作符约束 | “组织名称支持 `eq/in/like`，账期支持 `between`，年龄不允许分组” |
| 难表达跨字段规则 | “必须至少传一个账期字段过滤” |
| 难表达动作族规则 | `lookup` 不允许 `metrics`，`analyze` 不允许 `select` |
| 难表达术语解析规则 | `eq/in` 要翻标准术语，`like` 不翻 |
| 难表达 UI/Agent 指导语义 | “这个字段是维度-账期，不建议直接展示原始值” |

因此推荐：

- schema 中保留严格的结构定义
- 再加一层 `x-dc-*` 语义扩展
- 服务端统一做最终判定

---

## 4. MCP 字段约束的推荐总体方案

### 4.1 三层约束模型

#### 第一层：结构约束

由 JSON Schema 标准关键字表达：

- `type`
- `properties`
- `required`
- `enum`
- `const`
- `oneOf`
- `allOf`
- `if/then`
- `minItems` / `maxItems`
- `minimum` / `maximum`
- `additionalProperties`

#### 第二层：语义约束

通过自定义扩展关键字表达，建议统一使用 `x-dc-*` 前缀：

| 扩展字段 | 说明 |
| --- | --- |
| `x-dc-action-family` | 动作族，如 `lookup` / `analyze` / `search` |
| `x-dc-field-role` | 字段分析角色，如 `dimension` / `measure` |
| `x-dc-field-kind` | 字段分析类型，如 `id` / `name` / `time` / `period` / `number` / `indicator` |
| `x-dc-allowed-ops` | 字段允许的操作符 |
| `x-dc-allowed-group-ops` | 字段允许的分组方式 |
| `x-dc-allowed-agg-ops` | 字段允许的聚合方式 |
| `x-dc-term-resolve-ops` | 哪些操作符触发术语标准化 |
| `x-dc-required-filter-group` | **字段级**：该字段属于哪个强制过滤组，如 `period`（用于 `filters.items` 内的字段描述） |
| `x-dc-required-filter-group` | **根节点级**：整个动作的强制过滤组列表，格式为字符串数组，如 `["period"]`（用于 `inputSchema` 根节点） |
| `x-dc-example-values` | 示例值 |
| `x-dc-display-name` | 供模型和 UI 理解的业务名称 |
| `x-dc-visible-level` | `direct` / `skill_only` / `hidden` |

> 说明：`x-dc-required-filter-group` 在字段级与根节点级均使用，但含义不同：字段级为字符串标识该字段属于哪个组，根节点级为数组声明整个动作必须满足哪些过滤组。生成器和 Validator 需按上下文区分处理。

#### 第三层：执行校验

由服务端统一执行以下校验：

1. 字段存在校验
2. 动作族字段白名单校验
3. 字段能力校验
4. 强制过滤校验
5. 术语翻译校验
6. 数据权限校验
7. limit / offset 上限校验
8. 旧协议兼容转换

### 4.2 推荐的生成策略

建议生成器输出两份信息：

1. MCP 工具定义
   - `name`
   - `title`
   - `description`
   - `inputSchema`

2. 虚拟动作说明文档
   - 面向门户、技能包、调试台
   - 用 Markdown 输出
   - 说明动作用途、字段能力、限制条件、示例

### 4.3 结合当前 OWL 的设计调整

结合当前 `import_package_owl_onto/ontology` 的对象 OWL，需要补充一个很关键的现实约束：

1. 当前对象字段 OWL 已经有 `ext_property`、`property_category`、`property_group` 等字段。
2. 当前 `datacloud-data` 的 OWL 解析器并没有把这些扩展字段读进 `OntologyField`。
3. 当前 `datacloud-knowledge` 的知识包预检明确禁止 `ontology/` 目录文件入库，因此不能把“维度/度量标识”首期设计为依赖知识库 `term.ext_attrs`。

所以文档方案需要调整为：

- 首期：字段级维度/度量标识放在对象 OWL 的 `ext_property` 中，内容使用 JSON 字符串，格式遵循实际 OWL 文件中的 `property_role_rule` 结构。
- 运行时：`datacloud-data` OWL parser 负责把 `ext_property` 解析到 `OntologyField.ext_attrs`。
- 生成器：从 `ext_attrs.property_role_rule` 读取 `property_role / rule_type` 等基础标识。
- 能力项如 `group_ops/filter_ops/agg_ops` 不在 OWL 中手填，而是由规则引擎按字段分类和数据源能力动态生成。
- 后续若 ontology 文件进入知识库，再考虑同步到 `term.ext_attrs`，但这不是首期前提。

**实际 OWL `ext_property` 结构**（以对象 OWL 中的真实写法为准）：

维度字段（名称类）：

```json
{"property_role_rule": {"property_role": "DIMENSION_ATTR", "rule_type": "name"}}
```

维度字段（ID 类）：

```json
{"property_role_rule": {"property_role": "DIMENSION_ATTR", "rule_type": "id"}}
```

维度字段（时间类）：

```json
{"property_role_rule": {"property_role": "DIMENSION_ATTR", "rule_type": "time"}}
```

度量字段（数值类）：

```json
{"property_role_rule": {"property_role": "MEASURE", "rule_type": "numerical"}}
```

**运行时映射规则**（OWL → 内部语义）：

| OWL `property_role` | OWL `rule_type` | 运行时 role | 运行时 kind |
|---|---|---|---|
| `DIMENSION_ATTR` | `id` | `dimension` | `id` |
| `DIMENSION_ATTR` | `name` | `dimension` | `name` |
| `DIMENSION_ATTR` | `time` | `dimension` | `time` |
| `MEASURE` | `numerical` | `measure` | `number` |
| `MEASURE` | `indicator` | `measure` | `indicator` |
| `MEASURE` | `period` | `dimension` | `period` |

推荐职责分层：

- OWL `ext_property`：只存 `property_role_rule`，包含 `property_role`（`DIMENSION_ATTR` / `MEASURE`）和 `rule_type`（`id` / `name` / `time` / `numerical` / `indicator` / `period`）
- 规则表：按 `property_role` + `rule_type` 组合定义默认 `filter_ops/group_ops/agg_ops`
- 数据源函数 profile：裁剪规则表产出的能力
- MCP 生成器：输出最终 `inputSchema`

**视图字段说明**：视图字段的 `property_role_rule` 来自视图对应的 `*_mapping.owl` 文件中各 `Mapping` 个体的 `ext_property`，不从源对象字段继承；物理列定位通过 Mapping 的 `source_object_code` + `source_object_column_code` 解析。

---

## 5. 字段约束如何写进 MCP inputSchema

### 5.1 推荐方案：严格模式 + 紧凑模式

字段约束建议分两种生成模式。

#### 模式 A：严格模式

适用于字段数较少的对象或视图，推荐阈值 `<= 20` 个可过滤字段。

做法：

- `filters.items` 使用 `oneOf`
- 每个字段生成一个独立 filter schema 分支
- 在每个分支中通过 `const + enum + typed value` 精确表达限制

优点：

- 约束最精确
- MCP 客户端和模型更容易理解
- 错误更早暴露

缺点：

- schema 体积会膨胀

#### 模式 B：紧凑模式

适用于字段数较多的对象或统计视图。

做法：

- `filters.items` 使用统一结构
- 所有字段目录放到根节点的 `x-dc-field-catalog`
- 服务端根据 catalog 和 validator 做最终判定

优点：

- schema 更短
- 适合大对象和大视图

缺点：

- 精确度略低
- 更多依赖服务端校验

### 5.2 生成策略建议

| 条件 | 生成模式 |
| --- | --- |
| 字段数量 `<= 20` | 严格模式 |
| 字段数量 `> 20` | 紧凑模式 |
| 对外公共 MCP 工具 | 优先严格模式 |
| 内部技能工具 | 可用紧凑模式 |

### 5.3 对严格模式阈值的优化建议

只用“字段数量”决定严格模式还不够，建议再加两个保护阈值：

1. `oneOf` 分支数阈值
   推荐当 `filters/dimensions/metrics` 任一处的候选分支数超过 `60` 时，自动切换为紧凑模式。
2. `inputSchema` 体积阈值
   推荐当生成后的 schema 超过 `48KB` 到 `64KB` 时，自动切换为紧凑模式。

原因是当前项目会把工具 definition 透传给：

- MCP `tools/list`
- 技能包生成器
- 规划器上下文

如果 schema 过大，会直接放大：

- MCP 首包体积
- 模型阅读成本
- 规划器 prompt 噪声

因此推荐把“字段数量”作为粗判，把“分支数 / schema 体积”作为最终开关。

---

## 6. 推荐的虚拟动作描述文档模板

虚拟动作除了 `inputSchema`，还应生成一份 Markdown 描述文档。建议模板如下。

### 6.1 文档模板

````md
# 动作：analyze_view_employee_stat

## 1. 基本信息
- 动作族：analyze
- 作用域：view
- 业务名称：员工统计分析
- 暴露策略：skill_only
- 适用场景：按账期、组织、城市等维度做统计分析

## 2. 何时使用
- 需要分组统计时使用
- 需要聚合指标时使用
- 不适用于查看明细列表

## 3. 强制限制
- 必须传账期过滤
- 不允许直接查询原始明细字段列表
- 度量字段只能出现在 metrics 中

## 4. 字段能力
| 字段 | 业务名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| period | 账期 | dimension | period | eq/in/between | month/quarter/year | 否 | 必须出现在 filters 中 |
| org_name | 组织名称 | dimension | name | eq/in/like | self | 否 | like 不做术语翻译 |
| profit | 利润 | measure | indicator | gt/gte/lt/lte | range | sum/avg/max/min | 指标字段 |

## 5. 输入示例
```json
{
  "dimensions": [{"field": "period", "group_op": "month"}],
  "metrics": [{"field": "profit", "agg": "sum", "as": "利润汇总"}],
  "filters": [{"field": "period", "op": "between", "value": ["2026-01", "2026-03"]}]
}
```

## 6. 常见错误
- 缺少账期过滤
- 维度字段写进 metrics
- 名称字段使用了不支持的聚合函数
````

### 6.2 描述文档生成规则

建议由生成器自动拼接以下内容：

| 段落 | 来源 |
| --- | --- |
| 动作名 / 动作族 / 作用域 | 动作 profile |
| 使用场景 | profile 模板 |
| 强制限制 | profile + field metadata |
| 字段能力表 | field metadata |
| 输入示例 | example generator |
| 常见错误 | validator rules |

---

## 7. MCP Tool Description 的推荐写法

### 7.1 顶层 description 模板

工具 description 不要只写“支持过滤和聚合”，建议统一模板：

```text
按规则对员工统计视图做聚合分析。仅支持配置中声明的维度、指标、过滤条件。必须包含账期过滤。适用于统计分析，不适用于明细列表查询。
```

### 7.2 description 建议包含四类信息

| 信息 | 是否必写 | 示例 |
| --- | --- | --- |
| 适用场景 | 是 | “适用于统计分析” |
| 禁止场景 | 是 | “不适用于明细列表” |
| 强制规则 | 是 | “必须包含账期过滤” |
| 限制来源 | 建议 | “仅支持配置中声明字段” |

### 7.3 推荐的 description 模板

#### `lookup`

```text
按条件查询员工明细。支持字段过滤、排序、分页；不支持聚合统计。仅允许使用配置中声明的字段和操作符。
```

#### `analyze`

```text
按规则对员工统计视图做分组统计。支持 dimensions + metrics + filters；不支持明细字段直接输出。必须满足账期等强制过滤规则。
```

#### `search`

```text
检索知识库文档。支持 query 与结构化过滤；不支持聚合统计。仅允许使用声明的筛选字段。
```

---

## 8. MCP inputSchema 设计说明

### 8.1 顶层结构设计原则

推荐所有虚拟动作统一以下设计原则：

1. 顶层字段数量尽量稳定。
2. 相同语义用相同字段名。
3. 明细与统计动作不要共用一套顶层参数。
4. 过滤条件统一用数组，不用 map。
5. 每个复杂子结构都要 `additionalProperties: false`。
6. 顶层显式声明 `scope_type` / `scope_code`，避免对象级和视图级工具在说明层混淆。

### 8.2 `lookup` 的 inputSchema 说明

#### 顶层字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `select` | `array[string]` | 否 | 返回字段列表 |
| `filters` | `array[FilterSpec]` | 否 | 过滤条件 |
| `order_by` | `array[OrderBySpec]` | 否 | 排序规则 |
| `limit` | `integer` | 否 | 返回上限 |
| `offset` | `integer` | 否 | 分页偏移 |

#### 推荐 schema 示例

```json
{
  "type": "object",
  "additionalProperties": false,
  "x-dc-action-family": "lookup",
  "x-dc-scope-type": "object",
  "x-dc-scope-code": "obj_employee",
  "properties": {
    "select": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["emp_id", "emp_name", "org_name", "city_name"]
      },
      "uniqueItems": true,
      "description": "返回字段列表；为空时返回默认字段"
    },
    "filters": {
      "type": "array",
      "items": {
        "oneOf": [
          {
            "title": "员工名称过滤",
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "field": {"const": "emp_name"},
              "op": {"type": "string", "enum": ["eq", "in", "like"]},
              "value": {
                "oneOf": [
                  {"type": "string"},
                  {"type": "array", "items": {"type": "string"}, "minItems": 1}
                ]
              }
            },
            "required": ["field", "op", "value"],
            "x-dc-field-role": "dimension",
            "x-dc-field-kind": "name",
            "x-dc-term-resolve-ops": ["eq", "in"]
          },
          {
            "title": "员工ID过滤",
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "field": {"const": "emp_id"},
              "op": {"type": "string", "enum": ["eq", "in"]},
              "value": {
                "oneOf": [
                  {"type": "string"},
                  {"type": "array", "items": {"type": "string"}, "minItems": 1}
                ]
              }
            },
            "required": ["field", "op", "value"],
            "x-dc-field-role": "dimension",
            "x-dc-field-kind": "id"
          }
        ]
      },
      "description": "过滤条件列表"
    },
    "order_by": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "field": {"type": "string", "enum": ["emp_id", "emp_name"]},
          "direction": {"type": "string", "enum": ["asc", "desc"]}
        },
        "required": ["field", "direction"]
      }
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 1000,
      "default": 100
    },
    "offset": {
      "type": "integer",
      "minimum": 0,
      "default": 0
    }
  }
}
```

### 8.3 `analyze` 的 inputSchema 说明

#### 顶层字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `dimensions` | `array[DimensionSpec]` | 否 | 分组维度 |
| `metrics` | `array[MetricSpec]` | 是 | 聚合指标（至少 1 项；纯维度枚举请用 `lookup`） |
| `filters` | `array[FilterSpec]` | 否 | 聚合前过滤条件 |
| `having` | `array[HavingSpec]` | 否 | 聚合后过滤条件，字段引用 `metrics.as` 别名 |
| `order_by` | `array[OrderBySpec]` | 否 | 排序规则 |
| `limit` | `integer` | 否 | 返回上限 |

#### 推荐 schema 示例

```json
{
  "type": "object",
  "additionalProperties": false,
  "x-dc-action-family": "analyze",
  "x-dc-scope-type": "view",
  "x-dc-scope-code": "view_employee_stat",
  "x-dc-required-filter-group": ["period"],
  "properties": {
    "dimensions": {
      "type": "array",
      "items": {
        "oneOf": [
          {
            "title": "账期维度",
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "field": {"const": "period"},
              "group_op": {"type": "string", "enum": ["month", "quarter", "year"]}
            },
            "required": ["field", "group_op"],
            "x-dc-field-role": "dimension",
            "x-dc-field-kind": "period",
            "x-dc-required-filter-group": "period"
          },
          {
            "title": "组织名称维度",
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "field": {"const": "org_name"},
              "group_op": {"type": "string", "enum": ["self"]}
            },
            "required": ["field", "group_op"],
            "x-dc-field-role": "dimension",
            "x-dc-field-kind": "name"
          }
        ]
      }
    },
    "metrics": {
      "type": "array",
      "minItems": 1,
      "items": {
        "oneOf": [
          {
            "title": "利润指标",
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "field": {"const": "profit"},
              "agg": {"type": "string", "enum": ["sum", "avg", "max", "min"]},
              "as": {"type": "string", "maxLength": 50}
            },
            "required": ["field", "agg"],
            "x-dc-field-role": "measure",
            "x-dc-field-kind": "indicator",
            "x-dc-allowed-agg-ops": ["sum", "avg", "max", "min"]
          },
          {
            "title": "员工ID计数指标",
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "field": {"const": "emp_id"},
              "agg": {"type": "string", "enum": ["count", "count_distinct"]},
              "as": {"type": "string", "maxLength": 50}
            },
            "required": ["field", "agg"],
            "x-dc-field-role": "measure",
            "x-dc-field-kind": "id"
          }
        ]
      }
    },
    "filters": {
      "type": "array",
      "items": {
        "oneOf": [
          {
            "title": "账期过滤",
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "field": {"const": "period"},
              "op": {"type": "string", "enum": ["eq", "in", "between"]},
              "value": {
                "if": {"properties": {"op": {"const": "between"}}},
                "then": {
                  "type": "array",
                  "items": {"type": "string"},
                  "minItems": 2,
                  "maxItems": 2,
                  "description": "between 需提供 [开始值, 结束值] 两元素数组"
                },
                "else": {
                  "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}, "minItems": 1}
                  ]
                }
              }
            },
            "required": ["field", "op", "value"],
            "x-dc-field-kind": "period",
            "x-dc-required-filter-group": "period"
          },
          {
            "title": "组织名称过滤",
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "field": {"const": "org_name"},
              "op": {"type": "string", "enum": ["eq", "in", "like"]},
              "value": {
                "oneOf": [
                  {"type": "string"},
                  {"type": "array", "items": {"type": "string"}, "minItems": 1}
                ]
              }
            },
            "required": ["field", "op", "value"],
            "x-dc-term-resolve-ops": ["eq", "in"]
          }
        ]
      }
    },
    "order_by": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "field": {"type": "string"},
          "direction": {"type": "string", "enum": ["asc", "desc"]}
        },
        "required": ["field", "direction"]
      },
      "description": "支持维度字段或 metrics.as 作为排序字段"
    },
    "having": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "field": {
            "type": "string",
            "description": "必须是 metrics.as 中定义的别名，不能是原始字段名"
          },
          "op": {"type": "string", "enum": ["eq", "gt", "gte", "lt", "lte"]},
          "value": {"type": "number"}
        },
        "required": ["field", "op", "value"]
      },
      "description": "聚合后过滤，等价于 SQL HAVING 子句"
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 500,
      "default": 100
    }
  },
  "required": ["metrics"]
}
```

### 8.4 `search` 的 inputSchema 说明

```json
{
  "type": "object",
  "additionalProperties": false,
  "x-dc-action-family": "search",
  "x-dc-scope-type": "object",
  "x-dc-scope-code": "kb_policy_doc",
  "properties": {
    "query": {
      "type": "string",
      "minLength": 1,
      "description": "检索词"
    },
    "filters": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "field": {"type": "string", "enum": ["doc_type", "owner", "status"]},
          "op": {"type": "string", "enum": ["eq", "in"]},
          "value": {
            "oneOf": [
              {"type": "string"},
              {"type": "array", "items": {"type": "string"}, "minItems": 1}
            ]
          }
        },
        "required": ["field", "op", "value"]
      }
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100,
      "default": 20
    }
  },
  "required": ["query"]
}
```

---

## 9. 推荐的扩展元数据目录

当字段较多时，建议把字段能力目录收敛到 schema 根节点。

### 9.1 `x-dc-field-catalog` 示例

当使用紧凑模式时，`x-dc-field-catalog` 替代逐字段 `oneOf`，`filters/dimensions/metrics` 的 `items` 改为通用结构，由服务端 Validator 参照 catalog 做精确校验：

```json
{
  "type": "object",
  "additionalProperties": false,
  "x-dc-action-family": "analyze",
  "x-dc-scope-type": "view",
  "x-dc-scope-code": "view_employee_stat",
  "x-dc-required-filter-group": "period",
  "x-dc-field-catalog": {
    "period": {
      "display_name": "账期",
      "role": "dimension",
      "kind": "period",
      "allowed_filter_ops": ["eq", "in", "between"],
      "allowed_group_ops": ["month", "quarter", "year"],
      "required_filter_group": "period"
    },
    "org_name": {
      "display_name": "组织名称",
      "role": "dimension",
      "kind": "name",
      "allowed_filter_ops": ["eq", "in", "like"],
      "allowed_group_ops": ["self"],
      "term_resolve_ops": ["eq", "in"]
    },
    "profit": {
      "display_name": "利润",
      "role": "measure",
      "kind": "indicator",
      "allowed_agg_ops": ["sum", "avg", "max", "min"]
    }
  },
  "properties": {
    "dimensions": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "field": {"type": "string", "description": "可用字段见 x-dc-field-catalog（role=dimension）"},
          "group_op": {"type": "string"},
          "buckets": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "from": {"type": ["number", "null"]},
                "to": {"type": ["number", "null"]},
                "label": {"type": "string"}
              }
            },
            "description": "range 分组时必填"
          }
        },
        "required": ["field", "group_op"]
      }
    },
    "metrics": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "field": {"type": "string", "description": "可用字段见 x-dc-field-catalog（role=measure），或 'count_all' 表示行数统计"},
          "agg": {"type": "string"},
          "as": {"type": "string", "maxLength": 50}
        },
        "required": ["agg"]
      }
    },
    "filters": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "field": {"type": "string", "description": "可用字段见 x-dc-field-catalog"},
          "op": {"type": "string"},
          "value": {}
        },
        "required": ["field", "op", "value"],
        "description": "字段能力约束见 x-dc-field-catalog，服务端 Validator 负责精确校验"
      }
    },
    "having": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "field": {"type": "string", "description": "必须是 metrics.as 定义的别名"},
          "op": {"type": "string", "enum": ["eq", "gt", "gte", "lt", "lte"]},
          "value": {"type": "number"}
        },
        "required": ["field", "op", "value"]
      }
    },
    "order_by": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "field": {"type": "string"},
          "direction": {"type": "string", "enum": ["asc", "desc"]}
        },
        "required": ["field", "direction"]
      }
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 500,
      "default": 100
    }
  },
  "required": ["metrics"]
}
```

> 注意：紧凑模式下，`filters.items` 使用通用结构，`field` 只有字符串约束，不做 `enum` 枚举。字段合法性由服务端读取 `x-dc-field-catalog` 后校验，不在 Schema 层拦截。这是紧凑模式精度低于严格模式的核心权衡。

### 9.2 为什么需要 catalog

因为对大视图逐字段生成 `oneOf` 会造成：

- schema 过长
- MCP 包太大
- 调试困难

所以：

- 小对象用严格模式
- 大视图用 catalog 模式

---

## 10. 服务端 Validator 的具体校验规则

### 10.1 推荐校验顺序

1. 兼容协议归一化
2. JSON Schema 结构校验
3. 动作族校验
4. 字段白名单校验
5. 操作符校验
6. 值类型校验
7. 强制过滤校验
8. 术语翻译校验
9. 权限校验
10. SQL / 检索计划生成前校验

这里的“兼容协议归一化”非常关键。因为当前项目线上真实虚拟动作协议还是：

- DB：`filters` 为 object map，配合 `aggregates + group_by`
- KB：`query + filters`

而新方案建议统一成数组式 `filters`、并拆成 `lookup / analyze / search`。因此服务端推荐先做：

- 旧 `query_*` 请求识别
- 旧 `filters: {field_code: {op, value}}` 转为新 `filters: [{field, op, value}]`
- 旧 `aggregates + group_by` 转为新 `metrics + dimensions`

归一化完成后，再进入 JSON Schema 和业务 Validator，避免同一套校验逻辑维护两份协议分支。

### 10.2 推荐错误返回

```json
{
  "code": "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP",
  "message": "字段 org_name 不支持操作符 gt",
  "detail": {
    "action": "analyze_view_employee_stat",
    "field": "org_name",
    "allowed_ops": ["eq", "in", "like"]
  }
}
```

### 10.3 必须由服务端校验的规则

以下规则不要只依赖 schema：

- 必须包含账期过滤
- measure 不能写到 `dimensions`
- dimension 不能写到 `metrics`
- 名称类字段 `like` 不做术语翻译
- 排序字段必须存在于输出列（维度字段或 `metrics.as` 别名）
- `having.field` 必须是 `metrics.as` 定义的别名，不能是原始字段名
- `limit` 不能超过 profile 的最大值
- `range` 分组必须携带 `buckets` 且至少有 2 个区间
- 低权限用户不能访问某些字段
- `scope_type=view` 的动作不能被错误路由到对象 `invoke_action()`
- `scope_type=view` 的动作不能被错误路由到对象执行器

---

## 11. 数据源函数差异的具体方案

### 11.1 问题定义

不同数据源对同一个业务函数的支持并不一致：

| 业务语义 | MYSQL | POSTGRESQL / OPENGAUSS | CLICKHOUSE | HIVE | SQLITE |
| --- | --- | --- | --- | --- | --- |
| 按月分组 | `DATE_FORMAT` / `MONTH` | `DATE_TRUNC('month', ...)` | `toStartOfMonth(...)` | 组合表达式 | `strftime(...)` |
| 按季分组 | `QUARTER(...)` | `DATE_TRUNC('quarter', ...)` | `toStartOfQuarter(...)` | 组合表达式 | 拼接表达式 |
| 中位数 | 往往不原生 | 可近似/窗口实现 | 常见原生或近似函数 | 一般不稳定 | 通常不支持 |
| TopN | 需排序+limit | 需排序+limit | 可原生优化 | 依赖执行计划 | 仅小数据可做 |

这意味着 MCP 不能直接把底层函数名暴露给模型，否则会导致：

- schema 和数据源强耦合
- 同一个动作在不同库上行为不一致
- 迁移数据源后 MCP 契约变化

### 11.2 设计原则

推荐遵循以下原则：

1. 对外只暴露“逻辑函数”，不暴露方言函数。
2. 虚拟动作生成器按数据源能力决定 schema 里哪些逻辑函数可见。
3. 执行层通过函数能力注册表把逻辑函数翻译成物理表达式。
4. 不支持的函数要么在 schema 层不暴露，要么在 validator 阶段拒绝，不要拖到 SQL 执行时报错。

### 11.3 逻辑函数模型

建议统一定义逻辑函数层：

| 逻辑函数族 | 逻辑函数 | 说明 |
| --- | --- | --- |
| 时间分组 | `day` / `month` / `quarter` / `year` | 对时间或账期字段分组 |
| 数值分桶 | `range` | 对数值或指标字段做区间分桶 |
| 基础聚合 | `count` / `count_distinct` / `sum` / `avg` / `max` / `min` | 默认可移植能力 |
| 高级聚合 | `median` / `topn` / `percentile` | 受数据源能力约束 |
| 过滤运算 | `eq` / `in` / `like` / `between` / `gt` / `gte` / `lt` / `lte` | 由字段 + 数据源共同约束 |

模型侧看到的永远是：

- `group_op=month`
- `agg=avg`
- `agg=median`

而不是：

- `DATE_TRUNC('month', col)`
- `toStartOfMonth(col)`
- `PERCENTILE_CONT(0.5)`

### 11.4 数据源函数能力注册表

建议新增统一注册表：

```python
@dataclass
class DatasourceFunctionProfile:
    db_type: str
    supported_group_ops: list[str]
    supported_filter_ops: list[str]
    supported_agg_ops: list[str]
    support_level: dict[str, str]  # native / rewrite / engine_fallback / reject
    expression_templates: dict[str, str]
```

推荐 support level 含义：

| level | 含义 |
| --- | --- |
| `native` | 数据源原生支持 |
| `rewrite` | 通过表达式改写支持 |
| `engine_fallback` | 通过本地聚合引擎或 `SQLITE_MEM` 支持 |
| `reject` | 不支持，不能暴露 |

### 11.5 推荐能力矩阵

首期建议定义如下默认矩阵：

| 逻辑函数 | MYSQL | POSTGRESQL | OPENGAUSS | CLICKHOUSE | HIVE | SQLITE |
| --- | --- | --- | --- | --- | --- | --- |
| `day` | native | native | native | native | rewrite | rewrite |
| `month` | native | native | native | native | rewrite | rewrite |
| `quarter` | native | native | native | native | rewrite | rewrite |
| `year` | native | native | native | native | native | rewrite |
| `range` | rewrite | rewrite | rewrite | rewrite | rewrite | engine_fallback |
| `count` | native | native | native | native | native | native |
| `count_distinct` | native | native | native | native | native | native |
| `sum/avg/max/min` | native | native | native | native | native | native |
| `median` | reject | engine_fallback | engine_fallback | native | reject | reject |
| `topn` | engine_fallback | engine_fallback | engine_fallback | rewrite | reject | reject |

### 11.6 虚拟动作生成规则

生成 `inputSchema` 时，应同时看：

1. 字段元数据能力
2. 动作 profile
3. 数据源函数 profile

最终规则：

- `allowed_group_ops = 字段允许分组 ∩ 数据源支持分组 ∩ 动作允许分组`
- `allowed_agg_ops = 字段允许聚合 ∩ 数据源支持聚合 ∩ 动作允许聚合`
- `allowed_filter_ops = 字段允许过滤 ∩ 数据源支持过滤`

例如：

- 字段 `profit` 是 `indicator`
- 字段元数据允许 `sum/avg/max/min/median`
- 当前数据源是 `MYSQL`
- 动作 profile 允许 `sum/avg/max/min/median`

则最终暴露给 MCP 的 `agg enum` 应为：

```json
["sum", "avg", "max", "min"]
```

因为 `median` 在 MySQL profile 中是 `reject`。

### 11.7 跨数据源场景

如果一个视图跨多个数据源，推荐分两种情况：

#### 情况 A：同源下推

- 所有对象属于同一个 `db_type`
- 直接按该 `db_type` profile 生成 schema

#### 情况 B：跨源聚合

- 多个对象来自不同数据源
- 默认不暴露各数据源私有函数
- 只暴露“可移植子集”或“本地聚合引擎子集”

推荐跨源默认子集：

- 时间分组：`day` / `month` / `quarter` / `year`
- 聚合：`count` / `count_distinct` / `sum` / `avg` / `max` / `min`
- 过滤：`eq` / `in` / `gt` / `gte` / `lt` / `lte` / `between` / `like`

### 11.8 在 MCP Schema 中如何体现

推荐增加以下扩展元数据：

| 扩展字段 | 说明 |
| --- | --- |
| `x-dc-db-type` | 当前动作主数据源类型 |
| `x-dc-supported-backends` | 支持的执行后端列表 |
| `x-dc-function-profile` | 当前函数能力 profile 名称 |
| `x-dc-support-level` | 对某函数的支持级别 |
| `x-dc-execution-strategy` | `native_sql` / `rewrite` / `engine_fallback` |

示例：

```json
{
  "field": {"const": "profit"},
  "agg": {"type": "string", "enum": ["sum", "avg", "max", "min"]},
  "x-dc-field-role": "measure",
  "x-dc-field-kind": "indicator",
  "x-dc-db-type": "MYSQL",
  "x-dc-function-profile": "mysql_v1",
  "x-dc-execution-strategy": {
    "sum": "native_sql",
    "avg": "native_sql",
    "max": "native_sql",
    "min": "native_sql"
  }
}
```

### 11.9 Validator 额外校验

针对函数能力，Validator 需要补以下检查：

1. 当前动作的 `db_type` 或执行后端是否已解析
2. 请求里的 `group_op` 是否被当前 backend 支持
3. 请求里的 `agg` 是否被当前 backend 支持
4. 若是 `engine_fallback`，当前 profile 是否允许 fallback
5. 若跨源，是否误用了单库私有函数

推荐错误示例：

```json
{
  "code": "VIRTUAL_ACTION_ERR_UNSUPPORTED_AGG",
  "message": "当前数据源 MYSQL 不支持聚合函数 median",
  "detail": {
    "field": "profit",
    "agg": "median",
    "db_type": "MYSQL",
    "allowed_aggs": ["sum", "avg", "max", "min"]
  }
}
```

---

## 12. 虚拟动作生成器的输出规范

建议虚拟动作生成器生成如下对象：

```python
{
    "tool": {
        "name": "analyze_view_employee_stat",
        "title": "员工统计分析",
        "description": "...",
        "inputSchema": {...}
    },
    "doc": {
        "markdown": "...",
        "summary": "...",
        "field_catalog": {...},
        "examples": [...]
    },
    "meta": {
        "action_family": "analyze",
        "scope_type": "view",
        "exposure_policy": "skill_only",
        "strict_mode": true,
        "db_type": "MYSQL",
        "function_profile": "mysql_v1"
    }
}
```

### 12.1 生成器最少输出项

| 字段 | 必须 | 说明 |
| --- | --- | --- |
| `tool.name` | 是 | MCP 工具名 |
| `tool.title` | 是 | 中文名 |
| `tool.description` | 是 | 场景 + 限制 + 强制规则 |
| `tool.inputSchema` | 是 | MCP 输入结构 |
| `doc.markdown` | 是 | 供门户和技能使用的说明文档 |
| `meta.action_family` | 是 | 动作族 |
| `meta.exposure_policy` | 是 | 暴露策略 |
| `meta.db_type` | 建议 | 主数据源类型 |
| `meta.function_profile` | 建议 | 函数能力 profile |

### 12.2 运行时还需要输出统一索引信息

结合当前项目的 MCP 调用链，生成器除了产出 tool/doc/meta 外，建议再补可执行索引项，至少包含：

```json
{
    "runtime": {
        "scope_type": "view",
        "scope_code": "view_employee_stat",
        "invoke_via": "view.invoke_action",
        "planner_visible": true,
        "legacy_aliases": ["query_obj_employee"]
    }
}
```

原因是当前 `mcp_handler.py` / `mcp_sdk_handler.py` 的 `tools/call` 路由是靠“扫描对象 `cls.actions`”找到 `action_code -> object_code`，它天然不认识视图级动作。首期若不补这层运行时索引，Schema 再漂亮也落不到执行链上。

这里的 runtime index 只负责回答两件事：

- 这个 tool 属于 object 还是 view
- 最终应该路由到 `obj.invoke_action()` 还是 `view.invoke_action()`

它不负责引入新的执行模型。真正执行仍然应复用现有 `Action.execute()`。

---

## 13. x-dc-* 扩展字段的安全性与兼容性

### 13.1 当前项目的 MCP 实现说明

当前 `datacloud-data` 使用的是 **官方 MCP SDK**（`mcp>=1.18.0`），不是 FastMCP。两者对 inputSchema 的处理有差异：

| 实现 | inputSchema 处理方式 | 自定义字段行为 |
| --- | --- | --- |
| 官方 MCP SDK | 透传，不做结构校验 | `x-dc-*` 完全透传给客户端 |
| FastMCP | 从 Python 函数签名自动推导 schema | 不支持手写 inputSchema，需要通过 annotations 传递 |

当前项目的 `ActionToolGenerator` 将 `Action.get_schema()` 的输出直接作为 `inputSchema` 传给 SDK，SDK 原样包装后通过 `tools/list` 返回。因此 `x-dc-*` 字段在当前实现中是安全的。

### 13.2 x-dc-* 的 JSON Schema 合法性

JSON Schema 规范（draft-07 及后续版本）明确允许 schema 对象中出现任意额外关键字（unknown keywords），这些关键字会被校验器忽略。因此：

- `x-dc-*` 放在 schema 的**根节点**或 `properties` 内的各字段定义上，均符合 JSON Schema 规范
- `additionalProperties: false` 约束的是**输入数据**中不能有额外的 key，**不约束 schema 对象本身**的额外关键字

这意味着：

```json
{
  "type": "object",
  "x-dc-action-family": "analyze",    ← schema 扩展关键字，合法
  "additionalProperties": false,       ← 约束输入数据不能有额外字段
  "properties": {
    "filters": {
      "items": {
        "x-dc-field-role": "dimension" ← 字段级扩展关键字，同样合法
      }
    }
  }
}
```

### 13.3 已知风险与规避建议

尽管 JSON Schema 允许扩展关键字，仍有以下风险需要注意：

| 风险场景 | 说明 | 规避方式 |
| --- | --- | --- |
| 严格 MCP 客户端 | 某些 MCP 客户端会对 tool definition 做严格解析，可能拒绝包含未知字段的 inputSchema | 将 `x-dc-*` 移到 Tool 的 `annotations` 字段 |
| Schema 体积膨胀 | `x-dc-*` 字段增加 schema 体积，放大 `tools/list` 首包和模型上下文 | 使用紧凑模式，将字段目录集中在根节点 `x-dc-field-catalog` |
| 客户端展示干扰 | 部分 MCP 客户端可能在 UI 中把 `x-dc-*` 当作可填字段展示 | 确保字段名以 `x-` 开头，符合 JSON Schema 扩展关键字约定 |

### 13.4 推荐放置策略

**策略一（当前推荐）：保留在 inputSchema，依赖 JSON Schema 扩展关键字规范**

- 优点：生成器简单，schema 和语义元数据在一起
- 缺点：体积略大，严格客户端有兼容风险

**策略二：x-dc-* 移到 Tool annotations 字段**

MCP 规范中 Tool 对象支持 `annotations` 字段，可用于存放任意元数据：

```json
{
  "name": "analyze_view_employee_stat",
  "description": "...",
  "inputSchema": { ...纯标准 JSON Schema... },
  "annotations": {
    "x-dc-action-family": "analyze",
    "x-dc-scope-type": "view",
    "x-dc-scope-code": "view_employee_stat",
    "x-dc-required-filter-group": ["period"],
    "x-dc-field-catalog": { ...字段目录... }
  }
}
```

- 优点：inputSchema 严格符合标准，兼容所有 MCP 客户端
- 缺点：生成器需分别维护两个结构；模型无法在 schema 内联看到字段语义

**策略三：x-dc-* 只在服务端内存保留，不序列化到 MCP 协议**

仅用于服务端 Validator 和规划器，不暴露给客户端。

- 优点：MCP 协议完全干净
- 缺点：客户端（包括调试台）无法获取字段语义信息

**首期建议：策略一（inputSchema 扩展关键字）+ 体积阈值切换紧凑模式**，后续若遇到严格客户端兼容问题，再按策略二迁移到 `annotations`。

---

## 14. 对当前项目的落地建议

### 14.1 生成器改造建议

当前 `dynamic_query_tool_generator.py` 主要是“按字段类型拼 schema”，建议改成：

1. 先读取字段分析元数据
2. 识别当前对象/视图的数据源类型或执行后端
3. 读取函数能力 profile
4. 构造字段能力目录
5. 计算字段能力与数据源能力的交集
6. 决定严格模式还是紧凑模式
7. 分别生成 `lookup/analyze/search` 的 `description`
8. 生成 `inputSchema`
9. 生成配套 Markdown 文档
10. 产出 `tool_name -> scope/invoke_via` 索引，供 MCP `tools/call` 直接路由

### 14.2 建议新增的生成函数

| 函数 | 职责 |
| --- | --- |
| `build_tool_description(profile, field_catalog)` | 生成 MCP description |
| `resolve_function_profile(scope)` | 解析当前 scope 的数据源函数能力 |
| `build_field_catalog(fields)` | 生成字段能力目录 |
| `build_lookup_schema(profile, field_catalog)` | 生成 lookup schema |
| `build_analyze_schema(profile, field_catalog)` | 生成 analyze schema |
| `build_search_schema(profile, field_catalog)` | 生成 search schema |
| `build_virtual_action_markdown(profile, field_catalog)` | 生成说明文档 |
| `build_runtime_action_index(specs)` | 生成 `tool_name -> scope/invoke_via` 路由索引 |

### 14.3 对象字段元数据建议

为了支撑上面的生成逻辑，字段元数据至少需要以下信息：

**OWL `ext_property` 中必须包含（实际规范源头）：**

- `ext_attrs.property_role_rule.property_role`：字段角色，取值 `DIMENSION_ATTR` / `MEASURE`
- `ext_attrs.property_rule_rule.rule_type`：细分类型，取值 `id` / `name` / `time` / `numerical` / `indicator` / `period`

**规则引擎动态生成（不写入 OWL）：**

- `filter_ops`：按 `rule_type` 推导支持的过滤操作
- `group_ops`：按 `rule_type` 推导支持的分组操作
- `aggregate_ops`：按 `property_role` 推导支持的聚合操作
- `term_resolve_ops`：按字段是否关联 term 词库推导
- `required_filter_group`：按对象定义的业务约束推导

**视图字段元数据来源**：视图字段的 `property_role_rule` 读取自 `*_mapping.owl` 中各 `Mapping` 个体的 `ext_property`，物理列位置通过 `source_object_code` + `source_object_column_code` 定位到具体对象表。

---

## 15. 最终建议

如果目标是”让 MCP 字段限制更清楚，模型更不容易乱用”，最佳实践不是继续堆 description 文本，而是：

1. 用动作族拆开输入协议。
2. 用严格模式 / 紧凑模式控制 schema 精度与体积。
3. 再加一层”数据源函数能力 profile”，解决不同数据库函数不一致的问题。
4. 用 `x-dc-*` 扩展元数据补充语义限制（放在 inputSchema 中或 Tool annotations 中，见第 13 节）。
5. 用 Markdown 动作文档补足可读性。
6. 用统一 Validator 做最终业务校验。
7. 用统一 runtime index 把 schema 生成和 `obj/view.invoke_action()` 路由接起来。

一句话总结：

`inputSchema` 负责”长什么样”，`x-dc-*` 负责”能怎么用”，`function profile` 负责”这个数据源能不能做”，`Validator` 负责”到底能不能执行”，`runtime index` 负责”最终该路由到 `obj.invoke_action()` 还是 `view.invoke_action()`”。

# 知识构建导入包规范 v1.0

> **给 LLM 的提示**：生成导入文件前请先阅读本文档，所有字段的合法值在第 3 节"字段枚举速查"中集中列出。

---

## 1. 导入包结构

```
导入包/
├── manifest.json               必须，清单文件，声明所有文件及执行顺序
├── meta/
│   ├── domains.json            低频，领域树定义
│   └── libraries.json          低频，知识库定义
├── term_types/
│   └── custom.json             中频，用户自定义术语类型（内置类型无需填写）
├── terms/
│   └── *.jsonl                 高频，JSONL 格式，每行一条术语，按领域拆分
├── relations/
│   └── *.jsonl                 高频，JSONL 格式，每行一条关系
└── ontology/
    ├── objects/                OBJ 类术语的详细定义 JSON
    ├── views/                  VIEW 类术语的详细定义 JSON
    ├── actions/                ACTION 类术语的详细定义 JSON
    └── functions/              FUNC 类术语的详细定义 JSON
```

**JSONL 格式说明**：每行是一个独立的合法 JSON 对象，行间无逗号，无外层数组。

---

## 2. 文件格式速查

### manifest.json

```json
{
  "version": "1.0",
  "package_id": "sales_init_20260318",
  "description": "本次导入说明",
  "created_at": "2026-03-18",
  "import_steps": [
    { "type": "meta",       "file": "meta/domains.jsonl",          "description": "..." },
    { "type": "meta",       "file": "meta/libraries.jsonl",         "description": "..." },
    { "type": "term_types", "file": "term_types/custom.jsonl",      "description": "..." },
    { "type": "terms",      "file": "terms/sales.jsonl",           "description": "...", "count": 13 },
    { "type": "relations",  "file": "relations/sales.jsonl",       "description": "...", "count": 5  }
  ]
}
```

### meta/domains.jsonl

```jsonl
{"op":"add","domain_code":"sales","domain_name":"销售领域","domain_desc":"..."}
{"op":"add","domain_code":"sales_crm","domain_name":"CRM子领域","parent_code":"sales"}
```

### meta/libraries.jsonl

```jsonl
{"op":"add","library_code":"crm_kb","library_name":"CRM知识库"}
{"op":"add","library_code":"hr_kb","library_name":"人力资源知识库"}
```

### term_types/custom.jsonl

```jsonl
{"op":"add","type_code":"CUSTOMER_TYPE","type_name":"客户类型","type_desc":"...","type_category":"字典术语","is_builtin":false}
```

### terms/*.jsonl（每行一条）

```jsonl
{"op":"add","term_code":"sales_customer","term_name":"客户","term_type_code":"ONTOLOGY_OBJ","domain_code":"sales","library_code":"crm_kb","owl_doc_file":"objects/sales_customer.json","desc_summary":"...","aliases":["客户信息"]}
{"op":"update","term_code":"sales_customer","desc_summary":"更新后的描述（只填需变更的字段）"}
{"op":"delete","term_code":"old_term"}
```

### relations/*.jsonl（每行一条）

```jsonl
{"op":"add","source_term_code":"po_users","target_term_code":"sales_customer","relation_name":"人员_维护_客户","relation_category":"BUSINESS","cardinality":"1:N","action_term_code":"action_query_customer"}
{"op":"delete","relation_code":"rel_obsolete_001"}
```

---

## 3. 字段枚举速查

### 3.1 通用字段

| 字段 | 合法值 | 说明 |
|------|--------|------|
| `op` | `add` \| `update` \| `delete` | 所有文件通用。`add` 时主键编码可省略（系统生成）；`update` / `delete` 时主键编码**必填** |

### 3.2 term_types/custom.json

| 字段 | 合法值 | 说明 |
|------|--------|------|
| `type_category` | `列表术语` \| `字典术语` \| `本体术语` \| `文档名称术语` | 系统导入时自动映射为数字 1/2/3/4 |
| `is_builtin` | `true` \| `false` | 导入文件中只填用户自定义类型，统一填 `false` |

### 3.3 terms/*.jsonl

| 字段 | 合法值 / 规则 | 说明 |
|------|---------------|------|
| `term_type_code` | 见下方【内置类型表】或 `term_types/custom.json` 中定义的 `type_code` | 必须已存在于系统 |
| `domain_code` | `meta/domains.json` 中定义的 `domain_code` | 必须已存在 |
| `library_code` | `meta/libraries.json` 中定义的 `library_code` | 可省略 |
| `owl_doc_file` | 相对于 `ontology/` 的路径，如 `objects/sales_customer.json` | 仅本体术语（`type_category=3`）填写，其余省略 |
| `term_code` | 小写英文 + 下划线，如 `sales_customer` | `add` 时可省略；建议填写，便于在 relations 中引用 |

### 3.4 relations/*.jsonl

| 字段 | 合法值 | 说明 |
|------|--------|------|
| `relation_category` | `ONTOLOGY` \| `BUSINESS` | **ONTOLOGY**：本体结构关系（包含、归属、继承等）；**BUSINESS**：业务语义关系（负责、创建、关联等） |
| `cardinality` | `1:1` \| `1:N` \| `N:1` \| `N:N` | 可省略，默认 `N:N` |
| `action_term_code` | `terms` 中 `term_type_code=ONTOLOGY_ACTION` 的 `term_code` | `BUSINESS` 关系推荐填写；`ONTOLOGY` 关系通常省略 |

---

## 4. 内置术语类型（系统预置，无需在导入包中声明）

| type_code | 名称 | type_category | 适用场景 |
|-----------|------|---------------|----------|
| `EMPLOYEE` | 员工 | 列表术语 (1) | 员工列表，关联人员维度 |
| `GENERAL` | 通用 | 字典术语 (2) | 通用枚举/字典，如状态、类别 |
| `ONTOLOGY_VIEW` | 视图 | 本体术语 (3) | 数据分析场景，包含多个对象 |
| `ONTOLOGY_OBJ` | 对象 | 本体术语 (3) | 业务实体，如客户、合同、组织 |
| `ONTOLOGY_ACTION` | 动作 | 本体术语 (3) | 业务操作，如查询、提交、审批 |
| `ONTOLOGY_FUNC` | 函数 | 本体术语 (3) | 可调用原子函数，如聚合函数 |
| `ONTOLOGY_PARAM` | 参数 | 本体术语 (3) | 动作/函数的输入输出参数 |
| `ONTOLOGY_PROP` | 属性 | 本体术语 (3) | 对象的字段/属性描述 |

---

## 5. 大数据量分片策略

单文件建议 **≤ 500 条**（兼顾 LLM 单次生成量与 git diff 可读性）。

超量时按领域或类型拆分，manifest 中依次列出：

```json
{ "type": "terms", "file": "terms/sales_obj.jsonl",   "count": 500 },
{ "type": "terms", "file": "terms/sales_action.jsonl", "count": 200 },
{ "type": "terms", "file": "terms/hr_obj.jsonl",       "count": 300 }
```

---

## 6. 给 LLM 的生成提示模板

```
你是知识图谱专家。请根据以下业务描述，生成术语导入 JSONL 文件。

规则：
- 每行一个 JSON 对象，字段含义参考上方【字段枚举速查】
- op 统一填 "add"
- term_type_code 从内置类型表中选择（如 ONTOLOGY_OBJ / ONTOLOGY_ACTION）
- term_code 使用小写英文+下划线，如 sales_customer
- 本体术语必须填 owl_doc_file，路径格式为 objects/xxx.json
- 只输出 JSONL 内容，不要输出任何解释文字

业务描述：
[在此粘贴业务需求]
```

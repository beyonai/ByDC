# 完整提示词与 JSON 用例（供测试）

**日期**: 2026-03-09  
**用途**: 在实现前，用完整 SYSTEM_PROMPT + objectView JSON + 用户问题 测试 LLM 输出效果

---

## 一、完整 SYSTEM_PROMPT（含新能力说明）

```
你是一个严格遵循元数据的数据查询计划生成器，**绝对禁止编造对象视图中不存在的表、字段、函数、条件**。所有SQL、条件、列必须100%来源于给定的 objectView，不允许脑补、推测、新增任何元数据中没有的内容。

根据「对象视图」和「用户问题」，生成一份结构化的查询执行计划（QueryExecutionPlan）。

## 输入
1. **对象视图（objectView）**：描述当前可用的数据源与对象能力，包括 sources（API/DB）、objects（字段与函数/表）、relations（对象间关联与 joinKeys）。
2. **用户问题（question）**：用户的自然语言查询。

## 对象视图中的 function 结构说明
- 每个 function 包含 **inputParams**（入参）和 **outputParams**（出参）：
  - **inputParams**：模型需要填写的入参，在 type:"API" 的 step 的 params 中填写，key 为 paramCode。
  - **outputParams**：返回结构说明，供理解后续步骤的 bindKey 或聚合列。
- 当 inputParams 中某参数有 **termSet** 时：
  - **termType: "enum"**：**必须**从 termLabels 中选取合法值，禁止自造或改写，否则会识别错。系统会解析为 code。
  - **termType: "lookup"** 或存在 **termHint**：该参数接受名称或ID，系统会在执行时解析，模型可直接填名称（如「营销一部」）。
- **优先单步**：当目标 API 的入参已有 termSet（termType: lookup）且能接受用户问题中的名称时，**直接在 params 中填写该名称**，无需先调用其他 API 获取 ID。系统会在执行时解析。优先使用单步查询，避免不必要的多步链式调用。
- 多步 API 链式调用：仅当目标 API 无法直接接受名称（无 term_set）或需从前序步骤取多行数据时，使用 **bindFromStep**（前序 stepId）、**bindKey**（列名）。

## 输出要求
请**仅输出一份合法的 JSON**，即 QueryExecutionPlan，不要包含其他解释或 markdown 代码块标记。结构约定如下：

- **canAnswer**（必填）：
  - 只有**所有查询条件、过滤字段、返回列都能在对象视图中找到**时，才为 true；
  - 只要缺少必要表、字段、API，或需要使用视图中**不存在的字段/条件**才能回答，一律为 false。

- 当 canAnswer 为 false 时：
  - 必须输出 **clarification** 字段（字符串类型，必填），内容需整合以下三类信息且表述完整：
    1. 无法回答的原因（明确说明缺少哪个字段/表/能力）；
    2. 向用户澄清需要补充的信息；
    3. 当前视图可查询的内容范围；
  - 禁止输出 steps、aggregation 字段，禁止输出除 canAnswer、clarification 外的任何多余字段。

- 当 canAnswer 为 true 时：
  - **steps**（必填）：查询步骤数组，不能为空。
    - 单DB表查询：生成 1 条 type:"SQL" 步骤，**只使用视图中已声明的表和字段**。
    - 同数据源多表关联查询（如同一DB下的多张表JOIN）：仅生成 1 条 type:"SQL" 步骤，直接在SQL中完成多表关联，**禁止拆分为多条SQL步骤**。
    - 跨数据源查询（API+DB/不同DB）：仅为每个数据源生成数据导出步骤（API步骤/DB查询步骤），标记csvTableName（CSV表名），**禁止生成额外的SQLITE_MEM类型步骤**。
    - 知识库检索：当 objectView 的 sources 中含 source_type 为 KNOWLEDGE_BASE 时，可生成 type:"KB" 步骤。KB 步骤需包含：stepId, type:"KB", datasourceAlias（数据源别名）, query（检索文本）, tags（可选，dict，field_code->value，用于按对象属性过滤）, outputRef。示例：{"stepId":"s1","type":"KB","datasourceAlias":"kb_ds","query":"用户问题关键词","tags":{"belong_emp_no":"xxx"},"outputRef":"kb_out"}
    - **API 步骤**：type:"API"，stepId, functionId（对应 functionCode）, params（入参，key 为 paramCode）, outputRef, csvTableName（跨数据源时必填）。若需从前序步骤取列值，增加 bindFromStep、bindKey。
  - **aggregation**（必填）：最终结果聚合规则。
    - strategy：
      - "DIRECT"：结果直接来自某条SQL（包括同数据源多表关联的SQL），无跨数据源计算。
      - "SQLITE_MEM"：跨数据源/API+DB 关联，基于各数据源导出步骤的CSV结果，在SQLite内存数据库中执行关联查询。
    - "DIRECT" 必须包含 finalStepId（指向唯一的SQL步骤ID）。
    - "SQLITE_MEM" 仅需包含 sqliteSql（基于steps中各CSV表名的SQLite关联查询语句），**禁止输出csvTables字段**。
    - columns：数组，每一项 {name, label, type}，**列必须来自视图已有字段**。
  - 禁止输出 clarification 字段，禁止输出除 canAnswer、steps、aggregation 外的任何多余字段。

## 铁律约束（必须严格遵守）
1. **严禁编造**：不允许使用对象视图中**不存在的表名、字段名、函数**，不允许凭空增加时间字段、状态字段、过滤条件。
2. 单表/同数据源多表查询：steps 仅输出 1 条SQL，多表关联直接在该SQL中通过JOIN实现。aggregation 使用 strategy=DIRECT。
3. 跨数据源/多数据源关联：必须使用 strategy=SQLITE_MEM。steps 仅包含各数据源的导出步骤。aggregation 中禁止输出csvTables字段，仅保留sqliteSql。
4. 禁止空步骤 steps=[] 且 finalStepId=null。
5. 禁止将同数据源的多表关联查询拆分为多条SQL步骤。
6. 输出的JSON中仅包含约定的字段，禁止出现任何未约定的多余字段。
```

---

## 二、完整 objectView JSON 用例

**数据来源**：`resources/ontology/crm_demo/objects_registry.json` 中的 po_users、po_organization 对象，经 inputParams/outputParams 拆分及 termSet/termType/termHint 增强。

```json
{
  "viewId": "crm_demo_view",
  "viewName": "CRM演示视图",
  "description": "包含组织、人员对象，基于 objects_registry.json",
  "sources": [
    {
      "sourceId": "SRC_API",
      "sourceType": "API",
      "datasourceAlias": ""
    }
  ],
  "objects": [
    {
      "objectId": "po_users",
      "objectName": "人员信息",
      "sourceId": "SRC_API",
      "table": "",
      "description": "主数据系统人员对象，包含用户基本信息、状态、组织归属等",
      "fields": [
        {"name": "userId", "type": "bigint", "description": "用户唯一标识"},
        {"name": "userName", "type": "string", "description": "用户名称"},
        {"name": "email", "type": "string", "description": "用户邮箱"},
        {"name": "phone", "type": "string", "description": "用户电话"},
        {"name": "userCode", "type": "string", "description": "用户登录标识"},
        {"name": "userNumber", "type": "string", "description": "工号"},
        {"name": "state", "type": "string", "description": "用户状态"},
        {"name": "orgId", "type": "string", "description": "组织ID"}
      ],
      "functions": [
        {
          "functionCode": "fn_po_users_query_by_ids",
          "description": "按用户ID列表或姓名列表批量查询人员详情",
          "inputParams": [
            {
              "paramCode": "userIds",
              "paramName": "用户名称或id列表",
              "paramType": "ARRAY",
              "termSet": "user.code",
              "termType": "lookup",
              "termHint": "接受名称或ID，系统会解析"
            }
          ],
          "outputParams": [
            {"paramCode": "userId", "paramName": "用户ID", "paramType": "STRING"},
            {"paramCode": "userName", "paramName": "用户名称", "paramType": "STRING"},
            {"paramCode": "userCode", "paramName": "工号", "paramType": "STRING"},
            {"paramCode": "orgId", "paramName": "组织ID", "paramType": "STRING"},
            {"paramCode": "state", "paramName": "用户状态", "paramType": "STRING"},
            {"paramCode": "email", "paramName": "邮箱", "paramType": "STRING"},
            {"paramCode": "phone", "paramName": "电话", "paramType": "STRING"}
          ]
        },
        {
          "functionCode": "fn_po_users_query_by_org",
          "description": "按组织ID查询该组织下的人员列表，可选是否包含下级组织",
          "inputParams": [
            {
              "paramCode": "orgId",
              "paramName": "组织ID",
              "paramType": "STRING",
              "required": true,
              "termSet": "org.code",
              "termType": "lookup",
              "termHint": "接受名称或ID，系统会解析；优先直接填名称，无需先查组织"
            },
            {
              "paramCode": "includeSubOrgs",
              "paramName": "是否包含下级组织",
              "paramType": "BOOLEAN",
              "required": false
            }
          ],
          "outputParams": [
            {"paramCode": "userId", "paramName": "用户ID", "paramType": "STRING"},
            {"paramCode": "userName", "paramName": "用户名称", "paramType": "STRING"},
            {"paramCode": "userNumber", "paramName": "工号", "paramType": "STRING"},
            {"paramCode": "orgId", "paramName": "所属组织ID", "paramType": "STRING"},
            {"paramCode": "state", "paramName": "用户状态", "paramType": "STRING"},
            {"paramCode": "email", "paramName": "邮箱", "paramType": "STRING"},
            {"paramCode": "phone", "paramName": "电话", "paramType": "STRING"}
          ]
        }
      ]
    },
    {
      "objectId": "po_organization",
      "objectName": "组织信息",
      "sourceId": "SRC_API",
      "table": "",
      "description": "主数据系统组织对象，包含组织层级、编码、类型等信息",
      "fields": [
        {"name": "orgId", "type": "bigint", "description": "组织ID"},
        {"name": "orgCode", "type": "string", "description": "组织编码"},
        {"name": "orgName", "type": "string", "description": "组织名称"},
        {"name": "orgType", "type": "string", "description": "组织类型"},
        {"name": "parentOrgId", "type": "bigint", "description": "父组织标识"},
        {"name": "orgLevel", "type": "integer", "description": "组织层级"},
        {"name": "orgDesc", "type": "string", "description": "组织描述"}
      ],
      "functions": [
        {
          "functionCode": "fn_po_org_query_by_ids",
          "description": "按组织ID列表或名称列表批量查询组织详情",
          "inputParams": [
            {
              "paramCode": "orgIds",
              "paramName": "组织ID或名称列表",
              "paramType": "ARRAY",
              "termSet": "org.code",
              "termType": "lookup",
              "termHint": "接受名称或ID，系统会解析"
            }
          ],
          "outputParams": [
            {"paramCode": "orgId", "paramName": "组织ID", "paramType": "STRING"},
            {"paramCode": "orgName", "paramName": "组织名称", "paramType": "STRING"},
            {"paramCode": "orgCode", "paramName": "组织编码", "paramType": "STRING"},
            {"paramCode": "parentOrgId", "paramName": "父组织ID", "paramType": "STRING"},
            {"paramCode": "orgLevel", "paramName": "组织层级", "paramType": "INTEGER"},
            {"paramCode": "orgType", "paramName": "组织类型", "paramType": "STRING"},
            {"paramCode": "orgDesc", "paramName": "组织描述", "paramType": "STRING"}
          ]
        },
        {
          "functionCode": "fn_po_org_query_sub_orgs",
          "description": "按组织ID查询其所有直接下级或全部下级组织",
          "inputParams": [
            {
              "paramCode": "orgId",
              "paramName": "组织名称或ID",
              "paramType": "STRING",
              "required": true,
              "termSet": "org.code",
              "termType": "lookup",
              "termHint": "接受名称或ID，系统会解析"
            },
            {
              "paramCode": "recursive",
              "paramName": "是否递归",
              "paramType": "BOOLEAN",
              "required": false
            }
          ],
          "outputParams": [
            {"paramCode": "orgId", "paramName": "组织ID", "paramType": "STRING"},
            {"paramCode": "orgName", "paramName": "组织名称", "paramType": "STRING"},
            {"paramCode": "orgCode", "paramName": "组织编码", "paramType": "STRING"},
            {"paramCode": "parentOrgId", "paramName": "父组织ID", "paramType": "STRING"},
            {"paramCode": "orgLevel", "paramName": "组织层级", "paramType": "INTEGER"},
            {"paramCode": "orgType", "paramName": "组织类型", "paramType": "STRING"}
          ]
        }
      ]
    }
  ],
  "relations": [
    {
      "fromObject": "po_organization",
      "toObject": "po_users",
      "joinKeys": [{"from": "orgId", "to": "orgId"}],
      "cardinality": "ONE_TO_MANY",
      "description": "组织与人员一对多"
    }
  ]
}
```

---

## 三、用户问题

```
查询营销一部销售人员的数量
```

---

## 四、User Message 组装示例

```
## 当前时间：
2026-03-09 14:00:00

## 输入内容

**对象视图：**
{上述 objectView JSON 完整粘贴}

**用户问题：**
查询营销一部销售人员的数量

请直接输出 QueryExecutionPlan 的 JSON，不要输出其他内容。
```

---

## 五、期望输出示例（QueryExecutionPlan）

**推荐（单步）**：因 `fn_po_users_query_by_org` 的 orgId 参数有 term_set，可直接填名称，无需先查组织：

```json
{
  "canAnswer": true,
  "steps": [
    {
      "stepId": "s1",
      "type": "API",
      "functionId": "fn_po_users_query_by_org",
      "params": {
        "orgId": "营销一部"
      },
      "outputRef": "users_out",
      "csvTableName": "users"
    }
  ],
  "aggregation": {
    "strategy": "SQLITE_MEM",
    "sqliteSql": "SELECT COUNT(*) AS cnt FROM users",
    "columns": [
      {"name": "cnt", "label": "数量", "type": "integer"}
    ]
  }
}
```

**说明**：
- Step1：直接用 `fn_po_users_query_by_org`，params 填 `orgId: "营销一部"`，系统执行时解析为 org ID
- Step2：SQLITE_MEM 聚合，统计 users 行数
- **无需** fn_po_org_query_by_ids，因术语转换可直接将名称转为 ID

**备选（多步）**：若 orgId 无 term_set 或需批量 bind 时，才用两步：Step1 查组织 → Step2 bind 查人员。

---

## 六、测试方式

1. 将「一、完整 SYSTEM_PROMPT」作为 system message
2. 将「四、User Message」作为 user message（objectView 用「二」的 JSON）
3. 调用 LLM，解析返回的 JSON
4. 检查：优先单步（直接用 fn_po_users_query_by_org，params.orgId: "营销一部"），而非两步（先 fn_po_org_query_by_ids 再 bind）

---

## 七、枚举类 term 示例（必读）

**问题**：若字段/参数的术语是枚举（如 status.code、priority.code），模型必须拿到枚举的合法值，否则会识别错（如自造「审批中」而实际应为「进行中」）。

**做法**：当 term_set 在 terms 配置中有静态条目时，序列化时注入 `termType: "enum"` 和 `termLabels`：

```json
{
  "paramCode": "status",
  "paramName": "待办状态",
  "paramType": "STRING",
  "required": false,
  "termSet": "status.code",
  "termType": "enum",
  "termLabels": ["待办", "进行中", "已完成", "已取消"]
}
```

```json
{
  "paramCode": "priority",
  "paramName": "优先级",
  "paramType": "STRING",
  "required": false,
  "termSet": "priority.code",
  "termType": "enum",
  "termLabels": ["高", "中", "低"]
}
```

**数据来源**：`termLabels` 由 TermLoader 从 terms 配置加载后，调用 `get_available_values(term_set)` 得到（返回各条目的 label 列表）。terms 配置格式见设计文档 3.1 节。

**对象字段**：若 object 的 field 有 term_set（如 reportStatus.code），序列化时同样注入 termLabels，供模型在 SQL 条件等场景使用。

---

## 八、完整可复制版本（一键测试）

以下为可直接复制到 LLM 对话的完整内容，基于「优先单步」设计。

### System Message（完整复制）

```
你是一个严格遵循元数据的数据查询计划生成器，**绝对禁止编造对象视图中不存在的表、字段、函数、条件**。所有SQL、条件、列必须100%来源于给定的 objectView，不允许脑补、推测、新增任何元数据中没有的内容。

根据「对象视图」和「用户问题」，生成一份结构化的查询执行计划（QueryExecutionPlan）。

## 输入
1. **对象视图（objectView）**：描述当前可用的数据源与对象能力，包括 sources（API/DB）、objects（字段与函数/表）、relations（对象间关联与 joinKeys）。
2. **用户问题（question）**：用户的自然语言查询。

## 对象视图中的 function 结构说明
- 每个 function 包含 **inputParams**（入参）和 **outputParams**（出参）：
  - **inputParams**：模型需要填写的入参，在 type:"API" 的 step 的 params 中填写，key 为 paramCode。
  - **outputParams**：返回结构说明，供理解后续步骤的 bindKey 或聚合列。
- 当 inputParams 中某参数有 **termSet** 时：
  - **termType: "enum"**：**必须**从 termLabels 中选取合法值，禁止自造或改写，否则会识别错。系统会解析为 code。
  - **termType: "lookup"** 或存在 **termHint**：该参数接受名称或ID，系统会在执行时解析，模型可直接填名称（如「营销一部」）。
- **优先单步**：当目标 API 的入参已有 termSet（termType: lookup）且能接受用户问题中的名称时，**直接在 params 中填写该名称**，无需先调用其他 API 获取 ID。系统会在执行时解析。优先使用单步查询，避免不必要的多步链式调用。
- 多步 API 链式调用：仅当目标 API 无法直接接受名称（无 term_set）或需从前序步骤取多行数据时，使用 **bindFromStep**（前序 stepId）、**bindKey**（列名）。

## 输出要求
请**仅输出一份合法的 JSON**，即 QueryExecutionPlan，不要包含其他解释或 markdown 代码块标记。结构约定如下：

- **canAnswer**（必填）：
  - 只有**所有查询条件、过滤字段、返回列都能在对象视图中找到**时，才为 true；
  - 只要缺少必要表、字段、API，或需要使用视图中**不存在的字段/条件**才能回答，一律为 false。

- 当 canAnswer 为 false 时：
  - 必须输出 **clarification** 字段（字符串类型，必填），内容需整合以下三类信息且表述完整：
    1. 无法回答的原因（明确说明缺少哪个字段/表/能力）；
    2. 向用户澄清需要补充的信息；
    3. 当前视图可查询的内容范围；
  - 禁止输出 steps、aggregation 字段，禁止输出除 canAnswer、clarification 外的任何多余字段。

- 当 canAnswer 为 true 时：
  - **steps**（必填）：查询步骤数组，不能为空。
    - 单DB表查询：生成 1 条 type:"SQL" 步骤，**只使用视图中已声明的表和字段**。
    - 同数据源多表关联查询（如同一DB下的多张表JOIN）：仅生成 1 条 type:"SQL" 步骤，直接在SQL中完成多表关联，**禁止拆分为多条SQL步骤**。
    - 跨数据源查询（API+DB/不同DB）：仅为每个数据源生成数据导出步骤（API步骤/DB查询步骤），标记csvTableName（CSV表名），**禁止生成额外的SQLITE_MEM类型步骤**。
    - 知识库检索：当 objectView 的 sources 中含 source_type 为 KNOWLEDGE_BASE 时，可生成 type:"KB" 步骤。KB 步骤需包含：stepId, type:"KB", datasourceAlias（数据源别名）, query（检索文本）, tags（可选，dict，field_code->value，用于按对象属性过滤）, outputRef。示例：{"stepId":"s1","type":"KB","datasourceAlias":"kb_ds","query":"用户问题关键词","tags":{"belong_emp_no":"xxx"},"outputRef":"kb_out"}
    - **API 步骤**：type:"API"，stepId, functionId（对应 functionCode）, params（入参，key 为 paramCode）, outputRef, csvTableName（跨数据源时必填）。若需从前序步骤取列值，增加 bindFromStep、bindKey。
  - **aggregation**（必填）：最终结果聚合规则。
    - strategy：
      - "DIRECT"：结果直接来自某条SQL（包括同数据源多表关联的SQL），无跨数据源计算。
      - "SQLITE_MEM"：跨数据源/API+DB 关联，基于各数据源导出步骤的CSV结果，在SQLite内存数据库中执行关联查询。
    - "DIRECT" 必须包含 finalStepId（指向唯一的SQL步骤ID）。
    - "SQLITE_MEM" 仅需包含 sqliteSql（基于steps中各CSV表名的SQLite关联查询语句），**禁止输出csvTables字段**。
    - columns：数组，每一项 {name, label, type}，**列必须来自视图已有字段**。
  - 禁止输出 clarification 字段，禁止输出除 canAnswer、steps、aggregation 外的任何多余字段。

## 铁律约束（必须严格遵守）
1. **严禁编造**：不允许使用对象视图中**不存在的表名、字段名、函数**，不允许凭空增加时间字段、状态字段、过滤条件。
2. 单表/同数据源多表查询：steps 仅输出 1 条SQL，多表关联直接在该SQL中通过JOIN实现。aggregation 使用 strategy=DIRECT。
3. 跨数据源/多数据源关联：必须使用 strategy=SQLITE_MEM。steps 仅包含各数据源的导出步骤。aggregation 中禁止输出csvTables字段，仅保留sqliteSql。
4. 禁止空步骤 steps=[] 且 finalStepId=null。
5. 禁止将同数据源的多表关联查询拆分为多条SQL步骤。
6. 输出的JSON中仅包含约定的字段，禁止出现任何未约定的多余字段。
```

### User Message（完整复制，含 objectView + 用户问题）

```
## 当前时间：
2026-03-09 14:00:00

## 输入内容

**对象视图：**
{"viewId":"crm_demo_view","viewName":"CRM演示视图","description":"包含组织、人员对象","sources":[{"sourceId":"SRC_API","sourceType":"API","datasourceAlias":""}],"objects":[{"objectId":"po_users","objectName":"人员信息","sourceId":"SRC_API","table":"","description":"主数据系统人员对象","fields":[{"name":"userId","type":"bigint","description":"用户唯一标识"},{"name":"userName","type":"string","description":"用户名称"},{"name":"orgId","type":"string","description":"组织ID"}],"functions":[{"functionCode":"fn_po_users_query_by_ids","description":"按用户ID列表或姓名列表批量查询人员详情","inputParams":[{"paramCode":"userIds","paramName":"用户名称或id列表","paramType":"ARRAY","termSet":"user.code","termType":"lookup","termHint":"接受名称或ID，系统会解析"}],"outputParams":[{"paramCode":"userId","paramName":"用户ID","paramType":"STRING"},{"paramCode":"userName","paramName":"用户名称","paramType":"STRING"},{"paramCode":"orgId","paramName":"组织ID","paramType":"STRING"}]},{"functionCode":"fn_po_users_query_by_org","description":"按组织ID查询该组织下的人员列表","inputParams":[{"paramCode":"orgId","paramName":"组织ID","paramType":"STRING","required":true,"termSet":"org.code","termType":"lookup","termHint":"接受名称或ID，系统会解析；优先直接填名称，无需先查组织"},{"paramCode":"includeSubOrgs","paramName":"是否包含下级组织","paramType":"BOOLEAN","required":false}],"outputParams":[{"paramCode":"userId","paramName":"用户ID","paramType":"STRING"},{"paramCode":"userName","paramName":"用户名称","paramType":"STRING"},{"paramCode":"orgId","paramName":"所属组织ID","paramType":"STRING"}]}]},{"objectId":"po_organization","objectName":"组织信息","sourceId":"SRC_API","table":"","description":"主数据系统组织对象","fields":[{"name":"orgId","type":"bigint","description":"组织ID"},{"name":"orgName","type":"string","description":"组织名称"}],"functions":[{"functionCode":"fn_po_org_query_by_ids","description":"按组织ID或名称列表批量查询组织详情","inputParams":[{"paramCode":"orgIds","paramName":"组织ID或名称列表","paramType":"ARRAY","termSet":"org.code","termType":"lookup","termHint":"接受名称或ID，系统会解析"}],"outputParams":[{"paramCode":"orgId","paramName":"组织ID","paramType":"STRING"},{"paramCode":"orgName","paramName":"组织名称","paramType":"STRING"}]}]}],"relations":[{"fromObject":"po_organization","toObject":"po_users","joinKeys":[{"from":"orgId","to":"orgId"}],"cardinality":"ONE_TO_MANY"}]}

**用户问题：**
查询营销一部销售人员的数量

请直接输出 QueryExecutionPlan 的 JSON，不要输出其他内容。
```

**说明**：上述 objectView 为紧凑 JSON（已精简字段），聚焦 po_users 的 fn_po_users_query_by_org（orgId 有 term_set）。若需完整版，使用「二」中的格式化 JSON。

### 期望输出（优先单步）

```json
{"canAnswer":true,"steps":[{"stepId":"s1","type":"API","functionId":"fn_po_users_query_by_org","params":{"orgId":"营销一部"},"outputRef":"users_out","csvTableName":"users"}],"aggregation":{"strategy":"SQLITE_MEM","sqliteSql":"SELECT COUNT(*) AS cnt FROM users","columns":[{"name":"cnt","label":"数量","type":"integer"}]}}
```

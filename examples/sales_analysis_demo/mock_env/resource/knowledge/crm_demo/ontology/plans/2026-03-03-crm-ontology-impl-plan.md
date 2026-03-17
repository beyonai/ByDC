# CRM 销售场景本体 JSON 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 基于销售场景概述，生成符合 dataCloud 标准格式的15个对象共享库 JSON + 4个场景 JSON + 生成脚本

**Architecture:** 维护一个 `objects_registry.json`（OBJECT 级，包含所有15个对象、14个函数、所有关系），编写 `generate_ontology.py` 脚本按场景过滤裁剪，输出4个自包含的 OBJECT 级场景 JSON 文件。

**Tech Stack:** Python 3（标准库 json）；本体格式遵循 dataCloud ontology v1.0 规范（scope: OBJECT）

**设计文档参考：** `datacloud-mock/docs/plans/2026-03-03-crm-ontology-design.md`
**本体格式规范：** `datacloud-data-service/docs/本地对象标准格式规范（JSON 、YAML 、OWL）.md`
**数据来源：** `datacloud-mock/docs/crm_demo/销售场景概述.md` § 2.2 各表 DDL

---

## Task 1: 创建目录并构建 objects_registry.json（函数 + API对象）

**Files:**
- Create: `datacloud-mock/docs/crm_demo/ontology/objects_registry.json`

**Step 1: 创建目录**

```bash
mkdir -p datacloud-mock/docs/crm_demo/ontology
```

**Step 2: 写入 objects_registry.json（文件顶层结构 + functions 部分）**

文件顶层结构：
```json
{
  "$schema": "https://datacloud.io/schemas/ontology/v1.0",
  "version": "1.0",
  "scope": "OBJECT",
  "metadata": {
    "name": "CRM销售场景本体共享库",
    "description": "销售场景所有对象、函数、关系的共享对象库",
    "author": "admin",
    "created_time": "2026-03-03T00:00:00Z",
    "tenant_id": "TENANT_001",
    "domain_ref": "sales"
  },
  "functions": [ /* 见下方 */ ],
  "objects": [ /* 见 Task 2-4 */ ],
  "relations": [ /* 见 Task 5 */ ]
}
```

functions 包含 14 个函数：
- `fn_query_mysql`：MySQL通用查询（api_schema，POST `/api/v1/query`，datasource_id=ds_crm）
- `fn_po_users_query_by_ids`：按名称/ID查人员（api_schema，GET `/api/v1/po/users/query`）
- `fn_po_users_query_by_org`：按组织ID查人员（api_schema，GET `/api/v1/po/users/by-org/{orgId}`）
- `fn_po_org_query_by_ids`：按名称/ID查组织（api_schema，GET `/api/v1/po/organizations/query`）
- `fn_po_org_query_sub_orgs`：查下级组织（api_schema，GET `/api/v1/po/organizations/{orgId}/children`）
- `fn_todo_create`：创建待办（api_schema，POST `/api/v1/todos`）
- `fn_todo_query_list`：查询待办列表（api_schema，POST `/api/v1/todos/list`）
- `fn_todo_accept`：接收待办（api_schema，PUT `/api/v1/todos/{todoId}/accept`）
- `fn_todo_return`：退回待办（api_schema，PUT `/api/v1/todos/{todoId}/return`）
- `fn_todo_process`：处理待办（api_schema，PUT `/api/v1/todos/batch/process`）
- `fn_todo_delete`：删除待办（api_schema，DELETE `/api/v1/todos/batch`）
- `fn_todo_urge`：催更待办（api_schema，POST `/api/v1/todos/batch/urge`）
- `fn_todo_update`：修改待办（api_schema，PUT `/api/v1/todos/{todoId}`）
- `fn_todo_approve`：审批待办（api_schema，PUT `/api/v1/todos/batch/approve`）

base_url 使用占位符：
- 主数据/人员/组织：`http://main-data-service:8080`
- 待办系统：`http://todo-service:8090`
- MySQL查询服务：`http://data-service:8082`

**Step 3: 验证 JSON 格式合法**

```bash
python3 -c "import json; json.load(open('datacloud-mock/docs/crm_demo/ontology/objects_registry.json')); print('JSON valid')"
```
Expected: `JSON valid`

**Step 4: Commit**

```bash
git add datacloud-mock/docs/crm_demo/ontology/objects_registry.json
git commit -m "feat(ontology): add functions to objects_registry"
```

---

## Task 2: objects_registry.json — 添加 API 类型对象（PoUsers、PoOrganization、TodoItems）

**Files:**
- Modify: `datacloud-mock/docs/crm_demo/ontology/objects_registry.json`（objects 数组）

**Step 1: 添加 po_users 对象**

```json
{
  "object_code": "po_users",
  "object_name": "人员对象",
  "object_type": "API",
  "source_system": "main_data_system",
  "domain_ref": "sales",
  "description": "主数据系统人员对象，对应 po_users 表",
  "tags": ["人员", "主数据"],
  "source_config": {
    "connector_type": "http",
    "base_url": "http://main-data-service:8080",
    "primary_key": "user_id",
    "display_column": "user_name"
  },
  "properties": [
    /* 与 po_users 表 DDL 字段一一对齐，包含：
       user_id, user_name, email, phone, user_code,
       address, remark, user_exp_date, create_date, update_date,
       state, is_locked, last_login_date, thumbnail_uri,
       ext_attr, user_number, station_id */
  ],
  "actions": [
    /* query_users_by_name_or_ids: function_refs=["fn_po_users_query_by_ids"]
       IN: names(Array)/userIds(Array)
       OUT: users(LIST) */
    /* query_users_by_org_id: function_refs=["fn_po_users_query_by_org"]
       IN: orgId(String)
       OUT: users(LIST) */
  ]
}
```

**Step 2: 添加 po_organization 对象**

```json
{
  "object_code": "po_organization",
  "object_name": "组织对象",
  /* 属性与 po_organization DDL 对齐：
     org_id, org_code, org_name, org_type, parent_org_id,
     org_level, org_index, create_date, update_date, path_code, org_desc */
  "actions": [
    /* query_org_by_name_or_id: IN: orgNames(Array)/orgIds(Array); OUT: orgs(LIST) */
    /* query_sub_orgs_by_org_id: IN: orgId(String); OUT: subOrgs(LIST) */
  ]
}
```

**Step 3: 添加 todo_items 对象（9个动作，与图片中 API 参数一一对应）**

属性与 todo_items DDL 对齐：
`id, title, todo_content, deadline_at, todo_priority, todo_status, created_by, promoter, org_id, handler_id, created_at, updated_at, completed_at, cancelled_at, cancelled_reason, approved_at, rejected_at, approval_comment, urgency_level, remark, meeting_note_id, return_reason, returned_at`

9个动作参数（基于图片）：
- `create_todo`：IN(deadlineAt, handlelds[], priority, urgencyLevel, content, meetingNoteId, title, promoter, remark)；OUT(todoId, errorMsg, status, title, createdAt)
- `query_todo_list`：IN(priority, urgencyLevel, orgId, meetingNoteIds[], statusList[], page, keyword, deadlineEnd, status, promoter, deadlineStart, pageSize, includeSubOrgs)；OUT(todoId, deadlineAt, approvalComment, priority, urgencyLevel, content, progress, status, ...)
- `accept_todo`：IN(todoId)；OUT(todoId, status)
- `return_todo`：IN(todoId, returnReason)；OUT(todoId, status)
- `process_todo`：IN(handleComment, progress, todoIds[])；OUT(todoId)
- `delete_todo`：IN(todoIds[])；OUT(deletedIds)
- `urge_todo`：IN(followUpContent, todoIds[])；OUT(todoId, followUpAt)
- `update_todo`：IN(todoId, planFinishTime, handlelds[], priority, urgencyLevel, content)；OUT(todoId)
- `approve_todo`：IN(approvalComment, approvalStatus, todoIds[])；OUT(todoId, approvalStatus)

**Step 4: 验证 JSON 合法**

```bash
python3 -c "import json; data=json.load(open('datacloud-mock/docs/crm_demo/ontology/objects_registry.json')); print(f'objects: {len(data[\"objects\"])}')"
```
Expected: `objects: 3`

**Step 5: Commit**

```bash
git add datacloud-mock/docs/crm_demo/ontology/objects_registry.json
git commit -m "feat(ontology): add API objects (po_users, po_organization, todo_items)"
```

---

## Task 3: objects_registry.json — 添加文档类型对象（SalesDailyReport、SalesMeetingNote）

**Files:**
- Modify: `datacloud-mock/docs/crm_demo/ontology/objects_registry.json`

**Step 1: 添加 sales_daily_report 对象**

```json
{
  "object_code": "sales_daily_report",
  "object_name": "日报对象",
  "object_type": "KNOWLEDGE_BASE",
  "source_system": "dingtalk",
  "domain_ref": "sales",
  "description": "钉钉来源日报记录，对应 sales_daily_report 表",
  "tags": ["日报", "非结构化"],
  "source_config": {
    "connector_type": "mysql",
    "datasource_id": "ds_crm",
    "table_name": "sales_daily_report",
    "primary_key": "id"
  },
  "properties": [
    /* 与 sales_daily_report DDL 对齐：
       id, report_date, report_title, report_content,
       report_status, belong_emp_no, belong_user_name,
       belong_emp_org_id, created_by, created_time,
       updated_by, updated_time */
  ],
  "actions": []
}
```

**Step 2: 添加 sales_meeting_note 对象**

属性与 sales_meeting_note DDL 对齐：
`id, meeting_title, meeting_content, start_time, related_bo_id, related_customer_id, participant_emp_nos, created_by, created_time, updated_by, updated_time`

**Step 3: 验证**

```bash
python3 -c "import json; data=json.load(open('datacloud-mock/docs/crm_demo/ontology/objects_registry.json')); print(f'objects: {len(data[\"objects\"])}')"
```
Expected: `objects: 5`

**Step 4: Commit**

```bash
git add datacloud-mock/docs/crm_demo/ontology/objects_registry.json
git commit -m "feat(ontology): add document objects (daily_report, meeting_note)"
```

---

## Task 4: objects_registry.json — 添加数据库类型对象（10个 ANALYTICS_DB）

**Files:**
- Modify: `datacloud-mock/docs/crm_demo/ontology/objects_registry.json`

按以下顺序逐个添加，属性严格与各表 DDL 字段对齐：

| 对象编码 | 表名 | datasource_id | 主键 |
|---|---|---|---|
| `sales_business_opportunity` | sales_business_opportunity | ds_crm | id |
| `sales_bo_status_change` | sales_bo_status_change | ds_crm | id |
| `po_users_kpi_detail` | po_users_kpi_detail | ds_crm | id |
| `sales_customer` | sales_customer | ds_crm | id |
| `sales_expense_report` | sales_expense_report | ds_crm | id |
| `po_users_kpi_summary` | po_users_kpi_summary | ds_crm | id |
| `po_users_kpi_completion` | po_users_kpi_completion | ds_crm | id |
| `sales_org_kpi_summary` | sales_org_kpi_summary | ds_crm | id |
| `sales_org_kpi_completion` | sales_org_kpi_completion | ds_crm | id |
| `sales_emp_attendance` | sales_emp_attendance | ds_attendance | id |

每个对象结构：
```json
{
  "object_code": "<编码>",
  "object_name": "<名称>",
  "object_type": "ANALYTICS_DB",
  "source_system": "crm_system",  /* 考勤用 attendance_system */
  "domain_ref": "sales",
  "description": "<描述>",
  "tags": ["CRM"],
  "source_config": {
    "connector_type": "mysql",
    "datasource_id": "<ds_crm 或 ds_attendance>",
    "table_name": "<表名>",
    "primary_key": "id"
  },
  "properties": [ /* 与 DDL 字段对齐 */ ],
  "actions": []
}
```

**Step 1: 验证全部15个对象**

```bash
python3 -c "
import json
data = json.load(open('datacloud-mock/docs/crm_demo/ontology/objects_registry.json'))
for o in data['objects']:
    print(o['object_code'], '-', o['object_type'])
print('Total:', len(data['objects']))
"
```

Expected（15行 + `Total: 15`）：
```
po_users - API
po_organization - API
todo_items - API
sales_daily_report - KNOWLEDGE_BASE
sales_meeting_note - KNOWLEDGE_BASE
sales_business_opportunity - ANALYTICS_DB
sales_bo_status_change - ANALYTICS_DB
po_users_kpi_detail - ANALYTICS_DB
sales_customer - ANALYTICS_DB
sales_expense_report - ANALYTICS_DB
po_users_kpi_summary - ANALYTICS_DB
po_users_kpi_completion - ANALYTICS_DB
sales_org_kpi_summary - ANALYTICS_DB
sales_org_kpi_completion - ANALYTICS_DB
sales_emp_attendance - ANALYTICS_DB
Total: 15
```

**Step 2: Commit**

```bash
git add datacloud-mock/docs/crm_demo/ontology/objects_registry.json
git commit -m "feat(ontology): add 10 ANALYTICS_DB objects to registry"
```

---

## Task 5: objects_registry.json — 添加 relations（对象关系）

**Files:**
- Modify: `datacloud-mock/docs/crm_demo/ontology/objects_registry.json`（relations 数组）

按 `销售场景概述.md` § 2.1.3 ER关系添加以下关系：

```json
"relations": [
  { "relation_name": "人员归属组织", "source_object_ref": "po_users", "target_object_ref": "po_organization", "relation_type": "BELONGS_TO", "cardinality": "MANY_TO_ONE", "source_property_ref": "org_id", "target_property_ref": "org_id" },
  { "relation_name": "组织父子层级", "source_object_ref": "po_organization", "target_object_ref": "po_organization", "relation_type": "BELONGS_TO", "cardinality": "MANY_TO_ONE", "source_property_ref": "parent_org_id", "target_property_ref": "org_id" },
  { "relation_name": "人员有个人KPI", "source_object_ref": "po_users", "target_object_ref": "po_users_kpi_summary", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "user_number", "target_property_ref": "emp_no" },
  { "relation_name": "人员有个人KPI完成统计", "source_object_ref": "po_users", "target_object_ref": "po_users_kpi_completion", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "user_number", "target_property_ref": "emp_no" },
  { "relation_name": "人员有合同", "source_object_ref": "po_users", "target_object_ref": "po_users_kpi_detail", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "user_number", "target_property_ref": "emp_no" },
  { "relation_name": "组织有合同", "source_object_ref": "po_organization", "target_object_ref": "po_users_kpi_detail", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "org_id", "target_property_ref": "emp_org_id" },
  { "relation_name": "组织有组织KPI", "source_object_ref": "po_organization", "target_object_ref": "sales_org_kpi_summary", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "org_id", "target_property_ref": "org_id" },
  { "relation_name": "组织有组织KPI完成统计", "source_object_ref": "po_organization", "target_object_ref": "sales_org_kpi_completion", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "org_id", "target_property_ref": "org_id" },
  { "relation_name": "人员有考勤", "source_object_ref": "po_users", "target_object_ref": "sales_emp_attendance", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "user_number", "target_property_ref": "emp_no" },
  { "relation_name": "人员有日报", "source_object_ref": "po_users", "target_object_ref": "sales_daily_report", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "user_number", "target_property_ref": "belong_emp_no" },
  { "relation_name": "商机有状态变更记录", "source_object_ref": "sales_business_opportunity", "target_object_ref": "sales_bo_status_change", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "id", "target_property_ref": "bo_id" },
  { "relation_name": "商机属于负责人", "source_object_ref": "po_users", "target_object_ref": "sales_business_opportunity", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "user_number", "target_property_ref": "iwhale_cbm_emp_no" },
  { "relation_name": "商机属于负责人组织", "source_object_ref": "po_organization", "target_object_ref": "sales_business_opportunity", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "org_id", "target_property_ref": "iwhale_cbm_org_id" },
  { "relation_name": "商机关联客户", "source_object_ref": "sales_business_opportunity", "target_object_ref": "sales_customer", "relation_type": "ASSOCIATES", "cardinality": "MANY_TO_ONE", "source_property_ref": "customer_name", "target_property_ref": "customer_name" },
  { "relation_name": "客户属于维护人", "source_object_ref": "po_users", "target_object_ref": "sales_customer", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "user_number", "target_property_ref": "iwhale_cbm_emp_no" },
  { "relation_name": "费用关联申请人", "source_object_ref": "po_users", "target_object_ref": "sales_expense_report", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "user_number", "target_property_ref": "applicant_emp_no" },
  { "relation_name": "费用关联申请组织", "source_object_ref": "po_organization", "target_object_ref": "sales_expense_report", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "org_id", "target_property_ref": "applicant_org_id" },
  { "relation_name": "费用关联商机", "source_object_ref": "sales_expense_report", "target_object_ref": "sales_business_opportunity", "relation_type": "ASSOCIATES", "cardinality": "MANY_TO_ONE", "source_property_ref": "related_bo_id", "target_property_ref": "opportunity_id" },
  { "relation_name": "费用关联客户", "source_object_ref": "sales_expense_report", "target_object_ref": "sales_customer", "relation_type": "ASSOCIATES", "cardinality": "MANY_TO_ONE", "source_property_ref": "related_customer_id", "target_property_ref": "id" },
  { "relation_name": "待办创建人", "source_object_ref": "po_users", "target_object_ref": "todo_items", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "user_id", "target_property_ref": "created_by" },
  { "relation_name": "会议纪要创建人", "source_object_ref": "po_users", "target_object_ref": "sales_meeting_note", "relation_type": "ASSOCIATES", "cardinality": "ONE_TO_MANY", "source_property_ref": "user_number", "target_property_ref": "created_by" },
  { "relation_name": "会议纪要关联商机", "source_object_ref": "sales_meeting_note", "target_object_ref": "sales_business_opportunity", "relation_type": "ASSOCIATES", "cardinality": "MANY_TO_ONE", "source_property_ref": "related_bo_id", "target_property_ref": "opportunity_id" },
  { "relation_name": "会议纪要关联客户", "source_object_ref": "sales_meeting_note", "target_object_ref": "sales_customer", "relation_type": "ASSOCIATES", "cardinality": "MANY_TO_ONE", "source_property_ref": "related_customer_id", "target_property_ref": "id" }
]
```

**Step 1: 验证 relations 数量**

```bash
python3 -c "
import json
data = json.load(open('datacloud-mock/docs/crm_demo/ontology/objects_registry.json'))
print('relations:', len(data['relations']))
"
```
Expected: `relations: 23`

**Step 2: Commit**

```bash
git add datacloud-mock/docs/crm_demo/ontology/objects_registry.json
git commit -m "feat(ontology): add 23 object relations to registry"
```

---

## Task 6: 编写 generate_ontology.py 脚本

**Files:**
- Create: `datacloud-mock/docs/crm_demo/ontology/generate_ontology.py`

**Step 1: 编写场景配置（每个场景声明所需对象编码）**

```python
SCENE_CONFIGS = {
    "scene_01_data_analysis": {
        "metadata_name": "在线查数分析场景",
        "description": "销售数据分析场景，支持简单查询、跨库联合检索、非结构化融合检索",
        "object_codes": [
            "po_users", "po_organization",
            "sales_business_opportunity", "po_users_kpi_summary",
            "po_users_kpi_detail", "sales_org_kpi_summary",
            "sales_customer", "sales_emp_attendance",
            "todo_items", "sales_daily_report"
        ]
    },
    "scene_02_behavior_mgmt": {
        "metadata_name": "销售行为管理场景",
        "description": "面向销售员工与主管的行为管理，打卡、待办、费用、会议纪要、日报一体化",
        "object_codes": [
            "po_users", "sales_emp_attendance",
            "todo_items", "sales_expense_report",
            "sales_business_opportunity", "sales_customer",
            "sales_meeting_note", "sales_daily_report"
        ]
    },
    "scene_03_insight_analysis": {
        "metadata_name": "销售洞察分析场景",
        "description": "人员立体画像与商机对赌分析，整合结构化与非结构化多源数据",
        "object_codes": [
            "po_users", "po_organization",
            "po_users_kpi_summary", "po_users_kpi_completion",
            "po_users_kpi_detail", "sales_org_kpi_summary",
            "sales_org_kpi_completion", "sales_business_opportunity",
            "sales_customer", "sales_expense_report",
            "sales_emp_attendance", "sales_daily_report",
            "sales_meeting_note", "todo_items"
        ]
    },
    "scene_04_decision_deduction": {
        "metadata_name": "销售决策推演场景",
        "description": "针对管理政策效果分析与突发事件应对的决策推演",
        "object_codes": [
            "po_users", "po_organization",
            "sales_business_opportunity", "sales_customer",
            "po_users_kpi_detail", "sales_emp_attendance",
            "sales_daily_report", "todo_items"
        ]
    }
}
```

**Step 2: 编写核心裁剪逻辑**

```python
import json
import os
from datetime import datetime

def load_registry(registry_path):
    with open(registry_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_scene(registry, scene_key, scene_config):
    object_codes = set(scene_config["object_codes"])
    
    # 过滤 objects（保留属性和动作）
    scene_objects = [o for o in registry["objects"] if o["object_code"] in object_codes]
    
    # 收集场景内 objects 动作引用的所有 function_codes
    needed_function_codes = set()
    for obj in scene_objects:
        for action in obj.get("actions", []):
            for fref in action.get("function_refs", []):
                needed_function_codes.add(fref)
            if "function_ref" in action:
                needed_function_codes.add(action["function_ref"])
    
    # 过滤 functions
    scene_functions = [f for f in registry["functions"] if f["function_code"] in needed_function_codes]
    
    # 过滤 relations（source 和 target 都在场景内）
    scene_relations = [
        r for r in registry["relations"]
        if r["source_object_ref"] in object_codes and r["target_object_ref"] in object_codes
    ]
    
    return {
        "$schema": "https://datacloud.io/schemas/ontology/v1.0",
        "version": "1.0",
        "scope": "OBJECT",
        "metadata": {
            "name": scene_config["metadata_name"],
            "description": scene_config["description"],
            "author": "admin",
            "created_time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tenant_id": "TENANT_001",
            "domain_ref": "sales"
        },
        "functions": scene_functions,
        "objects": scene_objects,
        "relations": scene_relations
    }

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    registry_path = os.path.join(script_dir, "objects_registry.json")
    
    registry = load_registry(registry_path)
    
    for scene_key, scene_config in SCENE_CONFIGS.items():
        scene_data = extract_scene(registry, scene_key, scene_config)
        output_path = os.path.join(script_dir, f"{scene_key}.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(scene_data, f, ensure_ascii=False, indent=2)
        print(f"Generated: {scene_key}.json "
              f"({len(scene_data['objects'])} objects, "
              f"{len(scene_data['functions'])} functions, "
              f"{len(scene_data['relations'])} relations)")

if __name__ == "__main__":
    main()
```

**Step 3: 运行脚本验证输出**

```bash
cd datacloud-mock/docs/crm_demo/ontology
python3 generate_ontology.py
```

Expected:
```
Generated: scene_01_data_analysis.json (10 objects, X functions, Y relations)
Generated: scene_02_behavior_mgmt.json (8 objects, X functions, Y relations)
Generated: scene_03_insight_analysis.json (14 objects, X functions, Y relations)
Generated: scene_04_decision_deduction.json (8 objects, X functions, Y relations)
```

**Step 4: 验证每个场景文件 JSON 合法**

```bash
for f in scene_0*.json; do
    python3 -c "import json; json.load(open('$f')); print('$f: OK')"
done
```
Expected: 4行 `OK`

**Step 5: Commit**

```bash
git add datacloud-mock/docs/crm_demo/ontology/generate_ontology.py
git add datacloud-mock/docs/crm_demo/ontology/scene_0*.json
git commit -m "feat(ontology): add generate_ontology.py and 4 scene JSONs"
```

---

## Task 7: 最终验证——检查关键字段完整性

**Step 1: 验证 objects_registry.json 中所有对象属性数量合理**

```bash
python3 -c "
import json
data = json.load(open('datacloud-mock/docs/crm_demo/ontology/objects_registry.json'))
for o in data['objects']:
    props = len(o.get('properties', []))
    actions = len(o.get('actions', []))
    print(f\"{o['object_code']}: {props} properties, {actions} actions\")
"
```

**Step 2: 验证 TodoItems 的9个动作全部存在**

```bash
python3 -c "
import json
data = json.load(open('datacloud-mock/docs/crm_demo/ontology/objects_registry.json'))
todo = next(o for o in data['objects'] if o['object_code'] == 'todo_items')
expected = {'create_todo','query_todo_list','accept_todo','return_todo','process_todo','delete_todo','urge_todo','update_todo','approve_todo'}
actual = {a['action_code'] for a in todo.get('actions', [])}
missing = expected - actual
print('Missing actions:', missing if missing else 'None')
"
```
Expected: `Missing actions: None`

**Step 3: 验证各场景文件中对象与关系自洽（关系引用的对象均在该场景内）**

```bash
python3 -c "
import json, glob
for fp in sorted(glob.glob('datacloud-mock/docs/crm_demo/ontology/scene_0*.json')):
    data = json.load(open(fp))
    codes = {o['object_code'] for o in data['objects']}
    broken = [r for r in data['relations'] if r['source_object_ref'] not in codes or r['target_object_ref'] not in codes]
    print(f'{fp}: relations_ok={len(broken)==0}, objects={len(codes)}, relations={len(data[\"relations\"])}')
"
```
Expected: 4行均 `relations_ok=True`

**Step 4: 最终 Commit**

```bash
git add .
git commit -m "feat(ontology): complete CRM sales scene ontology JSON generation"
```

---

## 产物汇总

| 文件 | 说明 |
|---|---|
| `objects_registry.json` | 共享对象库（15对象、14函数、23关系） |
| `scene_01_data_analysis.json` | 在线查数分析（10对象） |
| `scene_02_behavior_mgmt.json` | 销售行为管理（8对象） |
| `scene_03_insight_analysis.json` | 销售洞察分析（14对象） |
| `scene_04_decision_deduction.json` | 销售决策推演（8对象） |
| `generate_ontology.py` | 生成脚本（从共享库裁剪4个场景） |

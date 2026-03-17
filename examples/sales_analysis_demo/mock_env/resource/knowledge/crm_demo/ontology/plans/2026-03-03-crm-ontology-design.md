# CRM 销售场景本体 JSON 设计文档

**日期**：2026-03-03  
**作者**：admin  
**领域**：sales / crm  

---

## 1. 背景与目标

基于 `销售场景概述.md` 中 § 2.4 场景用例，为四个销售业务场景构造符合 dataCloud 本体标准格式规范（`本地对象标准格式规范（JSON、YAML、OWL）.md`）的本地对象 JSON 文件。

**目标产物**：
- 一个共享对象库（`objects_registry.json`，OBJECT 级）
- 四个场景对象文件（OBJECT 级，各自自包含）
- 一个生成脚本（`generate_ontology.py`）

---

## 2. 文件结构

```
datacloud-mock/docs/crm_demo/ontology/
├── objects_registry.json              # 共享库：所有对象 + 函数 + 关系（唯一手工维护源）
├── scene_01_data_analysis.json        # 在线查数分析场景（自动生成）
├── scene_02_behavior_mgmt.json        # 销售行为管理场景（自动生成）
├── scene_03_insight_analysis.json     # 销售洞察分析场景（自动生成）
├── scene_04_decision_deduction.json   # 销售决策推演场景（自动生成）
└── generate_ontology.py               # 生成脚本
```

---

## 3. 对象清单

### 3.1 API 类型对象（含动作，通过 API 函数交互）

| 对象编码 | 对象名称 | 来源系统 | 动作 |
|---|---|---|---|
| `po_users` | 人员对象 | 主数据系统 | `query_users_by_name_or_ids`、`query_users_by_org_id` |
| `po_organization` | 组织对象 | 主数据系统 | `query_org_by_name_or_id`、`query_sub_orgs_by_org_id` |
| `todo_items` | 待办事项对象 | 待办系统 | `create_todo`、`query_todo_list`、`accept_todo`、`return_todo`、`process_todo`、`delete_todo`、`urge_todo`、`update_todo`、`approve_todo` |

### 3.2 文档类型对象（KNOWLEDGE_BASE，只有属性，无动作）

| 对象编码 | 对象名称 | 来源系统 | 对应表 |
|---|---|---|---|
| `sales_daily_report` | 日报对象 | 钉钉 | `sales_daily_report` |
| `sales_meeting_note` | 会议纪要对象 | 钉钉 | `sales_meeting_note` |

### 3.3 数据库类型对象（ANALYTICS_DB，只有属性，无动作）

| 对象编码 | 对象名称 | 来源系统 | 数据库 | 对应表 |
|---|---|---|---|---|
| `sales_business_opportunity` | 商机对象 | 宜搭CRM | MySQL | `sales_business_opportunity` |
| `sales_bo_status_change` | 商机状态变更对象 | 宜搭CRM | MySQL | `sales_bo_status_change` |
| `po_users_kpi_detail` | 合同对象 | 宜搭CRM | MySQL | `po_users_kpi_detail` |
| `sales_customer` | 客户对象 | 宜搭CRM | MySQL | `sales_customer` |
| `sales_expense_report` | 费用报备对象 | 宜搭CRM | MySQL | `sales_expense_report` |
| `po_users_kpi_summary` | 个人KPI对象 | 宜搭CRM | MySQL | `po_users_kpi_summary` |
| `po_users_kpi_completion` | 个人KPI完成统计对象 | 宜搭CRM | MySQL | `po_users_kpi_completion` |
| `sales_org_kpi_summary` | 组织KPI对象 | 宜搭CRM | MySQL | `sales_org_kpi_summary` |
| `sales_org_kpi_completion` | 组织KPI完成统计对象 | 宜搭CRM | MySQL | `sales_org_kpi_completion` |
| `sales_emp_attendance` | 员工考勤对象 | 考勤系统 | MySQL | `sales_emp_attendance` |

**共 15 个对象**（不含 TodoItemHandlers）

---

## 4. 函数清单

### 4.1 DB 查询函数

| 函数编码 | 函数名 | 类型 | 说明 |
|---|---|---|---|
| `fn_query_mysql` | MySQL 通用查询 | API | 供所有 ANALYTICS_DB 对象查询使用 |

### 4.2 API 对象专属函数（每个动作对应一个函数）

| 函数编码 | 对应对象 | 对应动作 |
|---|---|---|
| `fn_po_users_query_by_ids` | po_users | query_users_by_name_or_ids |
| `fn_po_users_query_by_org` | po_users | query_users_by_org_id |
| `fn_po_org_query_by_ids` | po_organization | query_org_by_name_or_id |
| `fn_po_org_query_sub_orgs` | po_organization | query_sub_orgs_by_org_id |
| `fn_todo_create` | todo_items | create_todo |
| `fn_todo_query_list` | todo_items | query_todo_list |
| `fn_todo_accept` | todo_items | accept_todo |
| `fn_todo_return` | todo_items | return_todo |
| `fn_todo_process` | todo_items | process_todo |
| `fn_todo_delete` | todo_items | delete_todo |
| `fn_todo_urge` | todo_items | urge_todo |
| `fn_todo_update` | todo_items | update_todo |
| `fn_todo_approve` | todo_items | approve_todo |

**共 14 个函数**

---

## 5. 四个场景引用关系

### 5.1 场景一：在线查数分析（scene_01_data_analysis）

**核心对象**：`sales_business_opportunity`

**引用对象**：
- po_users（人员）
- po_organization（组织）
- po_users_kpi_summary（个人KPI）
- po_users_kpi_detail（合同）
- sales_org_kpi_summary（组织KPI）
- sales_customer（客户）
- sales_emp_attendance（考勤）
- todo_items（待办）
- sales_daily_report（日报）

**关键关系**：
- po_users → sales_business_opportunity（负责人工号）
- po_users → po_users_kpi_detail（工号）
- po_users → po_users_kpi_summary（工号）
- po_users → sales_emp_attendance（工号）
- sales_business_opportunity → sales_customer（客户名称）
- po_users → todo_items（创建/发起人）
- po_users → sales_daily_report（工号）

### 5.2 场景二：销售行为管理（scene_02_behavior_mgmt）

**核心对象**：`po_users`

**引用对象**：
- sales_emp_attendance（考勤）
- todo_items（待办）
- sales_expense_report（费用报备）
- sales_business_opportunity（商机）
- sales_customer（客户）
- sales_meeting_note（会议纪要）
- sales_daily_report（日报）

**关键关系**：
- po_users → sales_emp_attendance
- po_users → todo_items
- po_users → sales_expense_report（申请人）
- po_users → sales_daily_report
- po_users → sales_meeting_note（创建人）
- sales_expense_report → sales_business_opportunity（关联商机）
- sales_expense_report → sales_customer（关联客户）

### 5.3 场景三：销售洞察分析（scene_03_insight_analysis）

**核心对象**：`po_users`

**引用对象**：
- po_users_kpi_summary、po_users_kpi_completion、po_users_kpi_detail（个人KPI体系）
- sales_org_kpi_summary、sales_org_kpi_completion（组织KPI体系）
- sales_business_opportunity、sales_customer（商机客户）
- sales_expense_report（费用）
- sales_emp_attendance（考勤）
- sales_daily_report、sales_meeting_note（非结构化）
- todo_items（待办派发）

**关键关系**：上述所有关系 + po_organization → sales_org_kpi_summary/completion

### 5.4 场景四：销售决策推演（scene_04_decision_deduction）

**核心对象**：`po_users`

**引用对象**：
- po_organization（组织树）
- sales_business_opportunity（商机）
- sales_customer（客户）
- po_users_kpi_detail（合同/业绩）
- sales_emp_attendance（考勤）
- sales_daily_report（日报）
- todo_items（任务派发）

**关键关系**：
- po_users → po_organization（归属）
- po_organization → po_organization（父子层级）
- po_users → sales_business_opportunity（负责人）

---

## 6. 生成脚本逻辑

```
generate_ontology.py
  1. 读取 objects_registry.json（全量对象/函数/关系）
  2. 读取场景配置（内嵌在脚本中，声明每个场景需要的 object_codes）
  3. 对每个场景：
     a. 过滤出该场景所需的 objects（含属性和动作）
     b. 收集这些 objects 动作引用的 function_refs，过滤出所需 functions
     c. 过滤出 source 和 target 都在场景内的 relations
     d. 拼装为自包含的 OBJECT 级 JSON
  4. 写出各场景 JSON 文件
```

---

## 7. JSON 格式规范遵从

- **scope**：`OBJECT`（无 views 节点）
- **API 类型函数**：使用 `api_schema`（OpenAPI 3.0.x），`base_url` 使用占位符（如 `http://main-data-service:8080`、`http://todo-service:8090`）
- **ANALYTICS_DB 对象**：`source_config.connector_type = "mysql"`，`datasource_id` 使用 `ds_crm`（CRM）、`ds_attendance`（考勤）
- **KNOWLEDGE_BASE 对象**：`source_config.connector_type = "mysql"`，`datasource_id = "ds_crm"`
- **属性字段**：与各表 DDL 字段名一一对齐
- **关系类型**：`BELONGS_TO`（多对一）、`ASSOCIATES`（关联）、`ONE_TO_MANY`（一对多）

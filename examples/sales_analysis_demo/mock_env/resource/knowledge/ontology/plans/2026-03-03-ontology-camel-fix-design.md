# Ontology CamelCase & Param Fix 设计文档

**日期**：2026-03-03
**目标**：修复 objects_registry.json 中的命名规范和参数结构问题

---

## 1. 变更规则

### 规则1：对象属性 property_code → camelCase
- `source_column` 保持 snake_case（映射真实 DB/API 字段）
- `property_code` 改为 camelCase
- 同步更新 `relations` 中的 `source_property_ref` / `target_property_ref`

### 规则2：动作参数 param_code → camelCase
- 所有 action params 的 `param_code` 改 camelCase
- `mapping_path` 中的字段名同步 camelCase

### 规则3：OUT 参数展开为平级，无外层 wrapper
- 废除 `LIST` / 嵌套 `ARRAY`/`OBJECT` 包裹结构
- 每个响应字段作为独立 OUT param，通过 `mapping_path` 表达层级

### 规则4：mapping_path 格式规范

| 场景 | 格式 |
|---|---|
| 数组元素字段 | `$.response.users[].userId` |
| 对象子字段 | `$.response.handler.handlerId` |
| 标量响应字段 | `$.response.todoId` |
| RequestBody 字段 | `$.requestBody.title` |
| Path parameter | `$.parameters.todoId` |
| Query parameter | `$.parameters.includeSubOrgs` |

### 规则5：函数 api_schema → camelCase + 补全 response schema
- requestBody properties key → camelCase
- response 200 schema properties 补全具体字段（camelCase）
- 数组 items 内补 properties 定义

---

## 2. 各动作 OUT 参数定义

### po_users

**query_users_by_name_or_ids** OUT：
- userId, userName, userNumber, orgId, state, email, phone
- mapping: `$.response.users[].userId` 等

**query_users_by_org_id** OUT：
- userId, userName, userNumber, orgId, state, email, phone
- mapping: `$.response.users[].userId` 等

### po_organization

**query_org_by_name_or_id** OUT：
- orgId, orgName, orgCode, parentOrgId, orgLevel, orgType, orgDesc
- mapping: `$.response.organizations[].orgId` 等

**query_sub_orgs_by_org_id** OUT：
- orgId, orgName, orgCode, parentOrgId, orgLevel, orgType
- mapping: `$.response.organizations[].orgId` 等

### todo_items

**create_todo** OUT：
- todoId(`$.response.todoId`), errorMsg(`$.response.errorMsg`), status(`$.response.status`), title(`$.response.title`), createdAt(`$.response.createdAt`)

**query_todo_list** OUT：
- todoId, title, status, priority, urgencyLevel, deadlineAt, content, progress, createdAt, promoter, approvalComment, approvedAt, completedAt, meetingNoteId, handleContent, returnReason
- mapping: `$.response.todos[].todoId` 等

**accept_todo** OUT：
- todoId(`$.response.todoId`), status(`$.response.status`)

**return_todo** OUT：
- todoId(`$.response.todoId`), status(`$.response.status`)

**process_todo** OUT：
- todoId(`$.response.todoId`)

**delete_todo** OUT：
- deletedIds(`$.response.deletedIds`)

**urge_todo** OUT：
- todoId(`$.response.todoId`), followUpAt(`$.response.followUpAt`)

**update_todo** OUT：
- todoId(`$.response.todoId`)

**approve_todo** OUT：
- todoId(`$.response.todoId`), approvalStatus(`$.response.approvalStatus`)

---

## 3. 实现方式

编写 `fix_camel_and_params.py` 脚本：
1. `snake_to_camel()` 工具函数
2. 遍历所有 objects → 转换 property_code
3. 遍历所有 relations → 转换 source/target_property_ref
4. 遍历所有 actions → 用硬编码的正确 params 替换（因为 OUT 结构变化较大）
5. 遍历所有 functions → 转换 api_schema requestBody key + 补全 response schema
6. 输出新的 objects_registry.json
7. 重新运行 generate_ontology.py 更新4个场景文件

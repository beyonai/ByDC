# ext_attrs 本体层级冗余方案（多跳查询性能）

## 1. 目标

在 **视图 → 对象 → 动作 → 函数** 的本体层级上，在对应术语的 `ext_attrs` 中**冗余存储直接下级的术语 ID 列表**，使多跳查询时减少对 `term_relation` 的反复 JOIN，用「读 term 行 + 按主键 IN 查询」替代多级关系展开，提升查询性能。

## 2. 方案评估

### 2.1 是否合理

- **合理**。理由简述如下：
  - **查询形态**：典型场景是「给定视图/对象/动作，查其下所有对象/动作/函数或整棵子树」。若只依赖 `term_relation`，需要多级 JOIN 或多次按关系表查询；在层级固定（VIEW→OBJ→ACTION→FUNC）且关系以 ONTOLOGY 为主时，在父节点冗余「直接子节点 term_id 列表」是常见的反范式手段。
  - **存储成本**：每个视图/对象/动作仅多存一个 ID 数组，量级小；`ext_attrs` 已存在且为 JSONB，无需改表结构。
  - **一致性**：以 `term_relation` 为**唯一事实来源**，冗余数据由同步脚本/任务根据关系表计算写入，避免双写不一致。
  - **适用边界**：仅针对「本体结构关系」（VIEW 拥有对象、对象拥有动作、动作拥有函数）；业务关系（BUSINESS）不参与此冗余。

### 2.2 风险与约束

| 风险/约束 | 说明 | 缓解 |
|-----------|------|------|
| 冗余与关系表不一致 | 若只改 term_relation 而不同步 ext_attrs，会出现脏读 | 约定：凡通过导入或 API 变更 ONTOLOGY 关系后，执行一次同步脚本（或接入导入流水线末尾） |
| 仅支持「直接下级」 | 只冗余一层子 ID，多跳需多次读 term | 设计如此；若需「视图下所有函数」可应用层先取 object_ids → action_ids → function_ids 再 IN 查，仍比多级 JOIN 简单 |
| key 命名空间 | 需与其它 ext_attrs 用法区分 | 统一放在 `ext_attrs.onto` 下，见下节 |

## 3. 设计方案

### 3.1 约定：ext_attrs.onto

在 `term.ext_attrs` 中预留 **`onto`** 命名空间，专门存放由 `term_relation` 中 **relation_category = 'ONTOLOGY'** 推导出的层级冗余：

- **视图术语**（`term_type_code = 'ONTOLOGY_VIEW'`）  
  - `ext_attrs.onto.object_ids`：该视图直接包含的**对象术语**的 `term_id` 数组（与 `term_relation` 中 source=本视图、target=ONTOLOGY_OBJ 的 target_term_id 一致）。

- **对象术语**（`term_type_code = 'ONTOLOGY_OBJ'`）  
  - `ext_attrs.onto.action_ids`：该对象直接拥有的**动作术语**的 `term_id` 数组（与 term_relation 中 source=本对象、target=ONTOLOGY_ACTION 的 target_term_id 一致）。

- **动作术语**（`term_type_code = 'ONTOLOGY_ACTION'`）  
  - `ext_attrs.onto.function_ids`：该动作直接调用的**函数术语**的 `term_id` 数组（与 term_relation 中 source=本动作、target=ONTOLOGY_FUNC 的 target_term_id 一致）。

- **函数术语**（`ONTOLOGY_FUNC`）  
  - 无「下级」，可不写 `onto` 或 `onto = {}`。

**类型与 key 对应关系：**

| 术语类型 (term_type_code) | ext_attrs.onto 中的 key | 含义 |
|---------------------------|-------------------------|------|
| ONTOLOGY_VIEW             | object_ids              | 直接包含的对象 term_id 列表 |
| ONTOLOGY_OBJ              | action_ids              | 直接拥有的动作 term_id 列表 |
| ONTOLOGY_ACTION           | function_ids            | 直接调用的函数 term_id 列表 |
| ONTOLOGY_FUNC             | （无）                  | 不写入 |

**JSON 示例：**

```json
// 某视图术语
{ "onto": { "object_ids": ["sales_customer", "sales_order"] } }

// 某对象术语
{ "onto": { "action_ids": ["sales_customer_query_customers", "sales_customer_update"] } }

// 某动作术语
{ "onto": { "function_ids": ["fn_query_list", "fn_expense_query"] } }
```

### 3.2 数据来源与同步策略

- **唯一事实来源**：`whale_datacloud.term_relation`（且仅 `relation_category = 'ONTOLOGY'` 的边参与计算）。
- **同步方式**：
  - **推荐**：在知识包导入（import-package/run）成功之后，执行一次「本体层级冗余同步」脚本（见下节），根据当前 term_relation 重算所有 VIEW/OBJ/ACTION 的 `ext_attrs.onto` 并写回 `term.ext_attrs`。
  - 也可由定时任务或运维在变更本体关系后手动执行同一脚本；脚本需**幂等**（多次执行结果一致）。

### 3.3 多跳查询用法（应用层）

- **单跳**：读该术语的 `ext_attrs.onto.object_ids`（或 action_ids / function_ids），再 `WHERE term_id = ANY($1)` 批量查 term 即可。
- **多跳**：例如「某视图下所有函数」：先取视图的 `object_ids` → 再读这些对象的 `action_ids` → 再取这些动作的 `function_ids`，合并去重后一次 `WHERE term_id = ANY($1)` 查函数术语；或每层各查一次 term 表（按主键 IN），避免对 term_relation 做多级 JOIN。

## 4. 已提供脚本

- **`db/ddl/whale_datacloud/99_sync_ontology_ext_attrs.sql`**（见下）：根据 `term_relation` 中 ONTOLOGY 关系，为所有 ONTOLOGY_VIEW / ONTOLOGY_OBJ / ONTOLOGY_ACTION 术语更新 `ext_attrs.onto` 的 object_ids / action_ids / function_ids；不覆盖 `ext_attrs` 中其它 key。导入或关系变更后执行一次即可。

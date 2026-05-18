# 项目任务表（by_project_task）

**类型**：object
**描述**：项目交付任务对象，记录项目启动、安装部署、交付、上线、收入确认和回款任务。

## 查询能力（query）

项目交付任务对象，记录项目启动、安装部署、交付、上线、收入确认和回款任务。

按条件查询对象项目任务表的明细记录。**select / filters.field / order_by.field 统一使用对象属性编码**；支持字段过滤、排序、分页；不支持聚合统计。

**何时使用**：查看具体记录列表时使用；不适用于统计汇总，如需统计请用 compute 动作。

**可用字段**：
| 字段编码 | 中文名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 主键 | measure | primary_key | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| project_code | 项目编码(ref: by_project.project_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| opp_code | 商机编码(ref: by_opportunity.opp_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| customer_code | 客户编码(ref: by_customer.customer_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| product_code | 产品编码(dict_type: product) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| project_task_type | 任务类型(同项目状态: 1项目启动 2安装部署 3项目交付 4项目上线 5收入确认 6完成回款) | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| initiator_user_id | 发起人用户编码(ref: po_users.user_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| handler_user_id | 处理人用户编码(ref: po_users.user_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| project_task_status | 任务状态(1处理中 2正常结束 3异常结束) | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| task_name | 任务名称 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| task_desc | 任务描述 | dimension | description | eq/in/like/is_null/is_not_null | - | - |  |
| handle_desc | 处理描述 | dimension | description | eq/in/like/is_null/is_not_null | - | - |  |
| initiate_time | 发起时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| plan_finish_time | 计划完成时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| actual_finish_time | 实际完成时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| create_by | 创建者 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| create_time | 创建时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| update_by | 更新者 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| update_time | 更新时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| remark | 备注 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |

**常见错误**：
- 使用了字段不支持的 op 操作符
- 将中文名、口语词或模糊概念猜测替换为相近属性编码
- 在 `select`、`filters.field`、`order_by.field` 中使用中文名而不是属性编码
- order_by 中用了 sort/op/order 键名，应统一使用 direction

## 统计能力（compute）

项目交付任务对象，记录项目启动、安装部署、交付、上线、收入确认和回款任务。

按规则对对象项目任务表做分组统计。**dimensions.field / metrics.field / filters.field 统一使用对象属性编码**；支持 dimensions + metrics + filters；不适合直接查看明细。

**何时使用**：需要分组统计、聚合指标时使用；不适用于查看明细列表，如需明细请用 query 动作。

**强制限制**：
- 度量字段只能出现在 `metrics` 中，不能作为维度
- `metrics` 不能为空

**字段能力**：
| 字段编码 | 中文名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 主键 | measure | primary_key | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| project_code | 项目编码(ref: by_project.project_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| opp_code | 商机编码(ref: by_opportunity.opp_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| customer_code | 客户编码(ref: by_customer.customer_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| product_code | 产品编码(dict_type: product) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| project_task_type | 任务类型(同项目状态: 1项目启动 2安装部署 3项目交付 4项目上线 5收入确认 6完成回款) | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| initiator_user_id | 发起人用户编码(ref: po_users.user_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| handler_user_id | 处理人用户编码(ref: po_users.user_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| project_task_status | 任务状态(1处理中 2正常结束 3异常结束) | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| task_name | 任务名称 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| task_desc | 任务描述 | dimension | description | eq/in/like/is_null/is_not_null | - | - |  |
| handle_desc | 处理描述 | dimension | description | eq/in/like/is_null/is_not_null | - | - |  |
| initiate_time | 发起时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| plan_finish_time | 计划完成时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| actual_finish_time | 实际完成时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| create_by | 创建者 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| create_time | 创建时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| update_by | 更新者 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| update_time | 更新时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| remark | 备注 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |

**常见错误**：
- `metrics` 为空（必须至少一个指标）
- `metrics` 项误用 `func` 表示聚合：必须使用键名 **`agg`**（如 `"agg": "count_distinct"`）
- 在 `dimensions.field`、`metrics.field`、`filters.field` 中使用中文名而不是属性编码
- `having.field` 未使用 `metrics` 中的 `as` 别名
- order_by 中用了 sort/op/order 键名，应统一使用 direction

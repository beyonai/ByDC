# 组织信息表（po_organization）

**类型**：object
**描述**：平台组织维度对象，承载客户、商机、项目所属组织及组织层级信息。

## 查询能力（query）

平台组织维度对象，承载客户、商机、项目所属组织及组织层级信息。

按条件查询对象组织信息表的明细记录。**select / filters.field / order_by.field 统一使用对象属性编码**；支持字段过滤、排序、分页；不支持聚合统计。

**何时使用**：查看具体记录列表时使用；不适用于统计汇总，如需统计请用 compute 动作。

**可用字段**：
| 字段编码 | 中文名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| org_id | org_id | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| org_code | org_code | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| org_name | org_name | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| org_type | org_type | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| parent_org_id | parent_org_id | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| org_level | org_level | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| org_index | org_index | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| create_date | create_date | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| update_date | update_date | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| path_code | path_code | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| org_desc | org_desc | dimension | description | eq/in/like/is_null/is_not_null | - | - |  |

**常见错误**：
- 使用了字段不支持的 op 操作符
- 将中文名、口语词或模糊概念猜测替换为相近属性编码
- 在 `select`、`filters.field`、`order_by.field` 中使用中文名而不是属性编码
- order_by 中用了 sort/op/order 键名，应统一使用 direction

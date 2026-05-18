# 商机信息表（by_opportunity）

**类型**：object
**描述**：销售商机对象，承载客户、产品、阶段状态、预测金额、签约金额和签约月份。

## 查询能力（query）

销售商机对象，承载客户、产品、阶段状态、预测金额、签约金额和签约月份。

按条件查询对象商机信息表的明细记录。**select / filters.field / order_by.field 统一使用对象属性编码**；支持字段过滤、排序、分页；不支持聚合统计。

**何时使用**：查看具体记录列表时使用；不适用于统计汇总，如需统计请用 compute 动作。

**可用字段**：
| 字段编码 | 中文名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 主键 | measure | primary_key | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| opp_code | 商机编码 | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| opp_name | 商机名称 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| industry | 所属行业 | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| domain | 所属领域(dict_type: domain) | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| customer_code | 所属客户编码(ref: by_customer.customer_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| sales_user_id | 所属销售用户编码(ref: po_users.user_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| dept_id | 所属组织编码(ref: po_organization.org_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| product_code | 所属产品编码(dict_type: product) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| opp_status | 商机状态(1线索获取 2方案交流 3商务报价 4签约成功 5签约失败) | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| forecast_amount | 预测金额 | measure | basic_metric | eq/in/gt/gte/lt/lte/is_null/is_not_null | range | sum/avg/min/max |  |
| contract_amount | 签约金额 | measure | basic_metric | eq/in/gt/gte/lt/lte/is_null/is_not_null | range | sum/avg/min/max |  |
| forecast_rate | 预测成功率(%) | measure | basic_metric | eq/in/gt/gte/lt/lte/is_null/is_not_null | range | sum/avg/min/max |  |
| fail_reason | 签约失败原因描述 | dimension | description | eq/in/like/is_null/is_not_null | - | - |  |
| success_summary | 签约成功总结 | dimension | description | eq/in/like/is_null/is_not_null | - | - |  |
| plan_sign_date | 计划签约日期(YYYY-MM-DD) | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| actual_sign_date | 实际签约日期(YYYY-MM-DD) | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
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

销售商机对象，承载客户、产品、阶段状态、预测金额、签约金额和签约月份。

按规则对对象商机信息表做分组统计。**dimensions.field / metrics.field / filters.field 统一使用对象属性编码**；支持 dimensions + metrics + filters；不适合直接查看明细。

**何时使用**：需要分组统计、聚合指标时使用；不适用于查看明细列表，如需明细请用 query 动作。

**强制限制**：
- 度量字段只能出现在 `metrics` 中，不能作为维度
- `metrics` 不能为空

**字段能力**：
| 字段编码 | 中文名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | 主键 | measure | primary_key | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| opp_code | 商机编码 | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| opp_name | 商机名称 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| industry | 所属行业 | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| domain | 所属领域(dict_type: domain) | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| customer_code | 所属客户编码(ref: by_customer.customer_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| sales_user_id | 所属销售用户编码(ref: po_users.user_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| dept_id | 所属组织编码(ref: po_organization.org_code) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| product_code | 所属产品编码(dict_type: product) | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| opp_status | 商机状态(1线索获取 2方案交流 3商务报价 4签约成功 5签约失败) | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| forecast_amount | 预测金额 | measure | basic_metric | eq/in/gt/gte/lt/lte/is_null/is_not_null | range | sum/avg/min/max |  |
| contract_amount | 签约金额 | measure | basic_metric | eq/in/gt/gte/lt/lte/is_null/is_not_null | range | sum/avg/min/max |  |
| forecast_rate | 预测成功率(%) | measure | basic_metric | eq/in/gt/gte/lt/lte/is_null/is_not_null | range | sum/avg/min/max |  |
| fail_reason | 签约失败原因描述 | dimension | description | eq/in/like/is_null/is_not_null | - | - |  |
| success_summary | 签约成功总结 | dimension | description | eq/in/like/is_null/is_not_null | - | - |  |
| plan_sign_date | 计划签约日期(YYYY-MM-DD) | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| actual_sign_date | 实际签约日期(YYYY-MM-DD) | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
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

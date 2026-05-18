# 用户信息表（po_users）

**类型**：object
**描述**：平台用户维度对象，承载销售、发起人、处理人等人员信息。

## 查询能力（query）

平台用户维度对象，承载销售、发起人、处理人等人员信息。

按条件查询对象用户信息表的明细记录。**select / filters.field / order_by.field 统一使用对象属性编码**；支持字段过滤、排序、分页；不支持聚合统计。

**何时使用**：查看具体记录列表时使用；不适用于统计汇总，如需统计请用 compute 动作。

**可用字段**：
| 字段编码 | 中文名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| user_id | 用户唯一标识 | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| user_name | 用户名称 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| email | 用户邮箱 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| phone | 用户电话 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| user_code | 用户登录标识 | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| pwd | 用户密码(md5加密) | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| address | 用户地址 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| remark | 用户备注 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| user_eff_date | 预留 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| user_exp_date | 用户过期日期 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| create_date | 记录创建日期 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| update_date | 记录更新日期 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| state | 用户状态：A-正常;X-禁用 | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| state_time | state_time | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| is_locked | 是否锁定，'Y'-锁定，'N'-没有锁定，null表示'N' | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| last_login_date | 用户最后一次登录时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| security_question_id | 用户忘记密码找回密码问题 | measure | raw_number | eq/in/gt/gte/lt/lte/is_null/is_not_null | range | sum/avg/min/max |  |
| security_answer | 用户忘记密码安全提示问题 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| thumbnail_uri | 用户头像URL地址 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| ext_attr | 用户扩展信息 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| assistant_id | 一个员工对应一个超级助手 | measure | raw_number | eq/in/gt/gte/lt/lte/is_null/is_not_null | range | sum/avg/min/max |  |
| user_number | 工号 | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| station_id | 所属驻地 | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| register_type | 注册类型 1-手机号注册 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| apple_user_id | 苹果用户ID，用于苹果登录关联 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |

**常见错误**：
- 使用了字段不支持的 op 操作符
- 将中文名、口语词或模糊概念猜测替换为相近属性编码
- 在 `select`、`filters.field`、`order_by.field` 中使用中文名而不是属性编码
- order_by 中用了 sort/op/order 键名，应统一使用 direction

## 统计能力（compute）

平台用户维度对象，承载销售、发起人、处理人等人员信息。

按规则对对象用户信息表做分组统计。**dimensions.field / metrics.field / filters.field 统一使用对象属性编码**；支持 dimensions + metrics + filters；不适合直接查看明细。

**何时使用**：需要分组统计、聚合指标时使用；不适用于查看明细列表，如需明细请用 query 动作。

**强制限制**：
- 度量字段只能出现在 `metrics` 中，不能作为维度
- `metrics` 不能为空

**字段能力**：
| 字段编码 | 中文名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| user_id | 用户唯一标识 | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| user_name | 用户名称 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| email | 用户邮箱 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| phone | 用户电话 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| user_code | 用户登录标识 | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| pwd | 用户密码(md5加密) | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| address | 用户地址 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| remark | 用户备注 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| user_eff_date | 预留 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| user_exp_date | 用户过期日期 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| create_date | 记录创建日期 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| update_date | 记录更新日期 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| state | 用户状态：A-正常;X-禁用 | dimension | name | eq/in/is_null/is_not_null | self | - |  |
| state_time | state_time | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| is_locked | 是否锁定，'Y'-锁定，'N'-没有锁定，null表示'N' | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| last_login_date | 用户最后一次登录时间 | dimension | datetime | eq/in/gt/gte/lt/lte/between/is_null/is_not_null | self/day/month/quarter/year | - |  |
| security_question_id | 用户忘记密码找回密码问题 | measure | raw_number | eq/in/gt/gte/lt/lte/is_null/is_not_null | range | sum/avg/min/max |  |
| security_answer | 用户忘记密码安全提示问题 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| thumbnail_uri | 用户头像URL地址 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| ext_attr | 用户扩展信息 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| assistant_id | 一个员工对应一个超级助手 | measure | raw_number | eq/in/gt/gte/lt/lte/is_null/is_not_null | range | sum/avg/min/max |  |
| user_number | 工号 | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| station_id | 所属驻地 | dimension | id | eq/in/is_null/is_not_null | self | count/count_distinct |  |
| register_type | 注册类型 1-手机号注册 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |
| apple_user_id | 苹果用户ID，用于苹果登录关联 | dimension | name | eq/in/like/is_null/is_not_null | self | - |  |

**常见错误**：
- `metrics` 为空（必须至少一个指标）
- `metrics` 项误用 `func` 表示聚合：必须使用键名 **`agg`**（如 `"agg": "count_distinct"`）
- 在 `dimensions.field`、`metrics.field`、`filters.field` 中使用中文名而不是属性编码
- `having.field` 未使用 `metrics` 中的 `as` 别名
- order_by 中用了 sort/op/order 键名，应统一使用 direction

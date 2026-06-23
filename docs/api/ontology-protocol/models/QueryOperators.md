# QueryOperators

带条件查询使用的操作符。`where` 参数接收一个嵌套查询对象，通过 `type` 字段区分操作符类型，支持 `and` / `or` / `not` 组合，最多三层深度。

## in

属性值在给定列表中，等于任意一个即命中。

**空数组 `[]` 表示匹配全部对象。**

| Name | Type | Required | Description |
|---|---|---|---|
| `type` | `"in"` | Yes | 操作符类型。 |
| `field` | string | Yes | 属性编码（propertyCode）。 |
| `value` | string[] | Yes | 匹配值列表。 |

```json
{ "type": "in", "field": "customer_code", "value": ["C001", "C002", "C003"] }
```

## eq

属性值等于给定值。

```json
{ "type": "eq", "field": "status", "value": "active" }
```

## and / or / not

布尔组合操作符。

```json
{
  "type": "and",
  "value": [
    { "type": "eq", "field": "industry", "value": "金融" },
    { "type": "in", "field": "province", "value": ["北京", "上海"] }
  ]
}
```

## 比较操作符

| type | 说明 |
|---|---|
| `gt` / `gte` | 大于 / 大于等于。 |
| `lt` / `lte` | 小于 / 小于等于。 |
| `isNull` | 是否为空。 |

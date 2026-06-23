# 带条件查询实例数据

```
POST /DtStudio/daiservice/InstanceController/search
```

根据对象类型和查询条件检索实例数据，返回匹配的对象列表。无需鉴权。

---

## Path Parameters

无

---

## Query Parameters

无

---

## Request Body

```
SearchInstancesRequest
```

### Schema

```json
{
  "objectCode": "by_customer",                         // string，必填。对象编码
  "select": ["customer_code", "customer_name"],        // string[]，可选。返回的属性编码列表
  "where": {                                           // object，可选。查询条件，留空返回全部
    "type": "in",                                      // string。操作符类型
    "field": "customer_code",                          // string。属性编码
    "value": ["C001", "C002", "C003"]                  // string[]。匹配值列表
  },
  "pageSize": 100,                                     // integer，可选。每页条数
  "pageToken": ""                                      // string，可选。分页游标
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `objectCode` | string | Yes | 对象编码。对象列表可通过 [getSceneDetails](../Scene/getSceneDetails.md) 的 `data.objects` 获取。 |
| `select` | string[] | No | 返回的属性编码列表。不传返回全部属性。 |
| `where` | object | No | 查询条件。`type` 决定操作符，支持 `and` / `or` / `not` 组合嵌套。不传返回该对象类型的全部实例。 |
| `pageSize` | integer | No | 每页条数。默认 `100`，上限 `1000`。 |
| `pageToken` | string | No | 分页游标。首次留空，后续取响应 `nextPageToken` 填入。 |

### 字段说明

> `where` 操作符定义见 [models/QueryOperators.md](../models/QueryOperators.md)

---

## Response Body

```
SearchInstancesResponse
```

### Schema

```json
{
  "code": 200,                                        // integer
  "success": true,                                    // boolean
  "message": "查询成功",                               // string
  "data": [                                           // array，失败时为 null
    {
      "id": 1,                                        // integer。主键
      "customer_code": "C001",                        // string
      "customer_name": "张三",                         // string
      "industry": "金融",                              // string
      "province": "北京",                              // string
      "city": "北京",                                  // string
      "domain": "银行",                                // string
      "sales_user_id": "U001",                        // string
      "sales_person": "王经理",                        // string
      "dept_id": "D001",                              // string
      "dept_name": "金融事业部",                        // string
      "remark": null,                                 // string，可选
      "create_time": "2024-01-15 10:30:00",           // string。YYYY-MM-DD HH:mm:ss
      "update_time": "2024-01-15 10:30:00"            // string
    }
  ],
  "nextPageToken": "v1.xxx",                          // string，可选
  "totalCount": 3                                     // integer
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | array | Yes | 实例数据列表。失败时为 `null`。 |
| `nextPageToken` | string | No | 下一页游标。最后一页无此字段。 |
| `totalCount` | integer | Yes | 全量命中总数。 |

> `data` 中各属性字段的 name/type 取决于对象的属性定义，参见 [models/Property.md](../models/Property.md)

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：objectCode不能为空` | `objectCode` 未传或为空 |
| `400` | 400 | `参数错误：未知操作符「{type}」` | `where.type` 不在支持范围内 |
| `404` | 404 | `未查询到对象类型「{objectCode}」` | 指定的 `objectCode` 不存在 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常 |

### Error Example

```json
{
  "code": 400,
  "success": false,
  "message": "参数错误：objectCode不能为空",
  "data": null
}
```

---

## Example

### in 操作符按编码查客户

查询 `by_customer` 对象中 `customer_code` 为 C001 / C002 / C003 的客户，只返回编码和名称。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/InstanceController/search" \
  -d '{
    "objectCode": "by_customer",
    "select": ["customer_code", "customer_name"],
    "where": {
      "type": "in",
      "field": "customer_code",
      "value": ["C001", "C002", "C003"]
    },
    "pageSize": 100
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "customer_code": "C001",
      "customer_name": "张三"
    },
    {
      "customer_code": "C002",
      "customer_name": "李四"
    },
    {
      "customer_code": "C003",
      "customer_name": "王五"
    }
  ],
  "totalCount": 3
}
```

### 组合条件查询

查询行业为"金融"且省份在北京或上海的客户。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/InstanceController/search" \
  -d '{
    "objectCode": "by_customer",
    "where": {
      "type": "and",
      "value": [
        {"type": "eq", "field": "industry", "value": "金融"},
        {"type": "in", "field": "province", "value": ["北京", "上海"]}
      ]
    }
  }'
```

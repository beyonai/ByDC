# 查询场景列表

```
POST /DtStudio/daiservice/OntologyScenceController/query
```

按关键词模糊查询场景列表。无需鉴权。

---

## Path Parameters

无

---

## Query Parameters

无

---

## Request Body

```
QueryScenesRequest
```

### Schema

```json
{
  "queryKeyword": ""                                  // string，可选。场景名称或编码关键词，留空查全部
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `queryKeyword` | string | No | 模糊查询关键词，匹配场景名称和场景编码。留空返回全部场景。 |

---

## Response Body

```
QueryScenesResponse
```

### Schema

```json
{
  "code": 200,                                        // integer
  "success": true,                                    // boolean
  "message": "查询成功",                               // string
  "data": [                                           // array，失败时为 null
    {
      "sceneId": "2064947287571644418",              // string
      "sceneName": "核心平台收入专题场景",              // string
      "sceneCode": "RevenueTopicDemo",               // string
      "sceneDesc": ""                                // string，可选
    }
  ]
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | array | Yes | 场景列表。失败时为 `null`。 |
| `data[].sceneId` | string | Yes | 场景唯一标识。 |
| `data[].sceneName` | string | Yes | 场景名称。 |
| `data[].sceneCode` | string | Yes | 场景编码。 |
| `data[].sceneDesc` | string | No | 场景描述。 |

> 公共字段定义见 [models/Scene.md](../models/Scene.md)

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `500` | 500 | `系统错误：{原因}` | 服务端异常 |

### Error Example

```json
{
  "code": 500,
  "success": false,
  "message": "系统错误：数据库连接超时",
  "data": null
}
```

---

## Example

### 按关键词查询场景

模糊查询名称或编码含"收入"的场景。

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/DtStudio/daiservice/OntologyScenceController/query" \
  -d '{
    "queryKeyword": "收入"
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
      "sceneId": "2064947287571644418",
      "sceneName": "核心平台收入专题场景",
      "sceneCode": "RevenueTopicDemo",
      "sceneDesc": ""
    }
  ]
}
```

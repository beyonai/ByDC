# 列出对象类型

```
GET /api/v1/ontologyBases/{ownerType}/{baseId}/objects
```

列出本体库下的对象类型摘要列表。LOCAL 从本地 Backend 读取，REMOTE 从外部服务获取。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。获取方式见 [listOntologyBases](../OntologyBase/listOntologyBases.md)。 |

---

## Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `keyword` | string | No | — | 对象编码/名称过滤关键词。 |

---

## Request Body

无

---

## Response Body

```
ListObjectsResponse
```

### Schema

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "objectCode": "by_customer",
      "objectName": "客户信息表",
      "objectSource": "DB",
      "objectDesc": "CRM 客户主数据对象。",
      "conceptType": "1",
      "fieldCount": 16,
      "actionCount": 4
    }
  ],
  "totalCount": 5
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | array | Yes | 对象摘要列表。失败时为 `null`。 |
| `data[].objectCode` | string | Yes | 对象编码。 |
| `data[].objectName` | string | Yes | 对象名称。 |
| `data[].objectSource` | string | No | 数据来源：`DB` / `DYNAMIC_TABLE` / `KNOWLEDGE_BASE`。 |
| `data[].objectDesc` | string | No | 对象描述。 |
| `data[].conceptType` | string | No | 概念类型：`1` 业务实体，`2` 活动实体。 |
| `data[].fieldCount` | integer | No | 字段数量。LOCAL 时返回。 |
| `data[].actionCount` | integer | No | 动作数量。LOCAL 时返回。 |
| `totalCount` | integer | Yes | 全量总数。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `本体库「{baseId}」不存在` | 指定本体库未注册。 |
| `404` | 404 | `本体库「{baseId}」不存在` | 指定本体库未注册。 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常。 |

### Error Example

```json
{
  "code": 404,
  "success": false,
  "message": "本体库「unknown」不存在",
  "data": null
}
```

---

## Example

### 列出库下全部对象

#### Request

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/crm_demo/objects"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "objectCode": "by_customer",
      "objectName": "客户信息表",
      "objectSource": "DB",
      "objectDesc": "CRM 客户主数据对象。",
      "conceptType": "1",
      "fieldCount": 16,
      "actionCount": 4
    },
    {
      "objectCode": "order_details",
      "objectName": "订单明细表",
      "objectSource": "DYNAMIC_TABLE",
      "objectDesc": "订单明细对象。",
      "conceptType": "1",
      "fieldCount": 20,
      "actionCount": 2
    }
  ],
  "totalCount": 2
}
```

# 列出关系

```
GET /api/v1/ontologyBases/{ownerType}/{baseId}/relations
```

列出本体库下的关系列表。支持按源对象或目标对象过滤。

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
| `sourceObjectCode` | string | No | — | 按源对象编码过滤。 |
| `targetObjectCode` | string | No | — | 按目标对象编码过滤。 |

---

## Request Body

无

---

## Response Body

```
ListRelationsResponse
```

### Schema

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "relationCode": "rel_customer_orders",
      "relationName": "客户关联订单",
      "relationCardinality": "1:N",
      "sourceObjectCode": "by_customer",
      "sourceObjectName": "客户信息表",
      "targetObjectCode": "order_details",
      "targetObjectName": "订单明细表",
      "relationDesc": "按客户编码关联。",
      "status": 1
    }
  ],
  "totalCount": 3
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | array | Yes | 关系列表。失败时为 `null`。 |
| `totalCount` | integer | Yes | 全量总数。 |

> `data[]` 元素定义见 [Relation](../../ontology-protocol/models/Relation.md)

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `本体库「{baseId}」不存在` | 指定本体库未注册。 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常。 |

---

## Example

### 列出全部关系

#### Request

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/crm_demo/relations"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "relationCode": "rel_customer_orders",
      "relationName": "客户关联订单",
      "relationCardinality": "1:N",
      "sourceObjectCode": "by_customer",
      "sourceObjectName": "客户信息表",
      "targetObjectCode": "order_details",
      "targetObjectName": "订单明细表",
      "relationDesc": "按客户编码关联。",
      "status": 1
    }
  ],
  "totalCount": 1
}
```

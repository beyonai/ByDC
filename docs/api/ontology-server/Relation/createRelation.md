# 创建关系

```
POST /api/v1/ontologyBases/{ownerType}/{baseId}/relations
```

创建关系。仅 LOCAL 可用。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |

---

## Request Body

```
CreateRelationRequest
```

### Schema

```json
{
  "relationCode": "rel_customer_orders",
  "relationName": "客户关联订单",
  "relationCardinality": "1:N",
  "sourceObjectCode": "by_customer",
  "targetObjectCode": "order_details",
  "relationDesc": "按客户编码关联。",
  "joinKeys": [
    {"fromField": "customer_code", "toField": "customer_code"}
  ]
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `relationCode` | string | Yes | 关系编码。不可重复。 |
| `relationName` | string | Yes | 关系名称。 |
| `relationCardinality` | string | Yes | `1:1` / `1:N` / `N:1` / `N:M`。 |
| `sourceObjectCode` | string | Yes | 源对象编码。必须已存在。 |
| `targetObjectCode` | string | Yes | 目标对象编码。必须已存在。 |
| `relationDesc` | string | No | 关系描述。 |
| `joinKeys` | array | No | 连接键映射。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "relationCode": "rel_customer_orders"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `403` | 403 | `Remote ontology base is read-only` | REMOTE 写操作。 |
| `404` | 404 | `未查询到对象类型「{code}」` | source/target 对象不存在。 |
| `409` | 409 | `关系「{relationCode}」已存在` | 编码重复。 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常。 |

---

## Example

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/crm_demo/relations" \
  -d '{
    "relationCode": "rel_customer_orders",
    "relationName": "客户关联订单",
    "relationCardinality": "1:N",
    "sourceObjectCode": "by_customer",
    "targetObjectCode": "order_details"
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "relationCode": "rel_customer_orders"
  }
}
```

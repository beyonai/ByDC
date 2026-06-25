# 创建动作

```
POST /api/v1/ontologyBases/{ownerType}/{baseId}/objects/{objectCode}/actions
```

在指定对象下创建动作。仅 LOCAL 可用。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |
| `objectCode` | string | 对象编码。获取方式见 [listObjects](../Object/listObjects.md)。 |

---

## Request Body

```
CreateActionRequest
```

### Schema

```json
{
  "actionCode": "create_by_customer",
  "actionName": "新增客户",
  "actionType": "operation",
  "actionDesc": "新增一条客户记录。",
  "params": [
    {
      "paramCode": "customerName",
      "paramName": "客户名称",
      "paramType": "STRING",
      "isRequired": 0,
      "direction": "IN",
      "mappingPath": "$.requestBody.customerName"
    }
  ],
  "requestUrl": "/api/by/customer/add",
  "requestMethod": "POST"
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `actionCode` | string | Yes | 动作编码。对象内不可重复。 |
| `actionName` | string | Yes | 动作名称。 |
| `actionType` | string | Yes | `query` / `operation`。 |
| `actionDesc` | string | No | 动作描述。 |
| `params` | array | No | 参数列表。 |
| `requestUrl` | string | No | 实际请求 URL。 |
| `requestMethod` | string | No | `GET` / `POST`。 |

> `params` 元素定义见 [ActionParam](../../ontology-protocol/models/ActionParam.md)

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "actionCode": "create_by_customer"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | object | Yes | 创建结果。 |
| `data.actionCode` | string | Yes | 创建的动作编码。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：actionCode 不能为空` | `actionCode` 未传。 |
| `403` | 403 | `Remote ontology base is read-only` | REMOTE 写操作。 |
| `404` | 404 | `未查询到对象类型「{objectCode}」` | 指定对象不存在。 |
| `409` | 409 | `动作「{actionCode}」已存在` | 编码重复。 |

---

## Example

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/crm_demo/objects/by_customer/actions" \
  -d '{
    "actionCode": "create_by_customer",
    "actionName": "新增客户",
    "actionType": "operation",
    "params": [
      {
        "paramCode": "customerName",
        "paramName": "客户名称",
        "paramType": "STRING",
        "direction": "IN"
      }
    ]
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "actionCode": "create_by_customer"
  }
}
```

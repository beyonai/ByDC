# 更新对象类型

```
PUT /api/v1/ontologyBases/{baseId}/objects/{objectCode}
```

全量替换对象类型定义。仅 LOCAL 可用。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `baseId` | string | 本体库 API 名称。 |
| `objectCode` | string | 对象编码。必须已存在。 |

---

## Query Parameters

无

---

## Request Body

```
UpdateObjectRequest
```

同 [createObject](createObject.md)，全量替换。

---

## Response Body

### Schema

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "objectCode": "by_customer"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | object | Yes | 更新结果。 |
| `data.objectCode` | string | Yes | 更新的对象编码。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `403` | 403 | `Remote ontology base is read-only` | REMOTE ontology base 写操作。 |
| `404` | 404 | `未查询到对象类型「{objectCode}」` | 指定对象不存在。 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常。 |

### Error Example

```json
{
  "code": 404,
  "success": false,
  "message": "未查询到对象类型「unknown」",
  "data": null
}
```

---

## Example

### 更新对象名称

#### Request

```bash
curl -X PUT \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/crm_demo/objects/by_customer" \
  -d '{
    "objectCode": "by_customer",
    "objectName": "客户信息表（已更新）",
    "objectSource": "DB",
    "properties": [...]
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "objectCode": "by_customer"
  }
}
```

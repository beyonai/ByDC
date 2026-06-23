# 删除对象类型

```
DELETE /api/v1/ontologyBases/{ownerType}/{baseId}/objects/{objectCode}
```

删除对象类型。仅 LOCAL 可用。删除前校验无 relation/action 引用。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。 |
| `objectCode` | string | 对象编码。 |

---

## Query Parameters

无

---

## Request Body

无

---

## Response Body

### Schema

```json
{
  "code": 200,
  "success": true,
  "message": "删除成功",
  "data": null
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | null | Yes | 删除操作无业务数据返回。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `403` | 403 | `Remote ontology base is read-only` | REMOTE 写操作。 |
| `404` | 404 | `未查询到对象类型「{objectCode}」` | 指定对象不存在。 |
| `409` | 409 | `对象被{count}个关系引用，无法删除` | 有 relation 引用。 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常。 |

### Error Example

```json
{
  "code": 409,
  "success": false,
  "message": "对象被2个关系引用，无法删除",
  "data": null
}
```

---

## Example

### 删除对象

#### Request

```bash
curl -X DELETE \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/crm_demo/objects/by_customer"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "删除成功",
  "data": null
}
```

# 删除本体库

```
DELETE /api/v1/ontologyBases/{ownerType}/{baseId}
```

删除本体库。LOCAL 时级联删除所有场景及资源；REMOTE 时仅取消注册，外部源不受影响。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `ownerType` | string | personal / enterprise |
| `baseId` | string | 本体库 API 名称。获取方式见 [listOntologyBases](listOntologyBases.md)。 |

---

## Query Parameters

无

---

## Request Body

无

---

## Response Body

```
DeleteNamespaceResponse
```

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

### 删除 LOCAL 本体库

#### Request

```bash
curl -X DELETE \
  "https://$HOSTNAME/api/v1/ontologyBases/personal/crm_demo"
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

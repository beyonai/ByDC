# 删除术语名称

```
DELETE /api/v1/knowledge/termNames/{nameId}
```

删除指定术语名称。标准名称（isPrimary=true）禁止删除。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `nameId` | string | 名称 ID。可通过 `listTermNames` 接口获取。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "删除成功",
  "data": null
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `403` | 403 | `标准名称禁止删除` | `isPrimary = true` |
| `404` | 404 | `未查询到术语名称「{nameId}」` | 名称不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库删除失败 |

---

## Example

```bash
curl -X DELETE \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termNames/nm_002"
```

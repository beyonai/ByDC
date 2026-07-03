# 删除术语类型

```
DELETE /api/v1/knowledge/termTypes/{typeCode}
```

删除指定术语类型。内置类型（isBuiltin=true）禁止删除。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `typeCode` | string | 类型编码。可通过 `listTermTypes` 接口获取。 |

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
| `403` | 403 | `内置术语类型「{typeCode}」禁止删除` | `isBuiltin = true` 时拒绝删除 |
| `404` | 404 | `未查询到术语类型「{typeCode}」` | 类型不存在 |
| `409` | 409 | `术语类型「{typeCode}」存在关联术语，无法删除` | 类型下有关联术语 |
| `500` | 500 | `系统错误：{原因}` | 数据库删除失败 |

---

## Example

```bash
curl -X DELETE \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termTypes/custom_type"
```

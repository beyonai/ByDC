# 删除术语

```
DELETE /api/v1/knowledge/terms/{termId}
```

删除指定术语。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `termId` | string | 术语 ID。可通过 `searchTerms` 接口获取。 |

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
| `404` | 404 | `未查询到术语「{termId}」` | 术语不存在 |
| `409` | 409 | `术语「{termId}」存在子术语，无法删除` | 术语下有子术语时拒绝删除 |
| `500` | 500 | `系统错误：{原因}` | 数据库删除失败 |

---

## Example

```bash
curl -X DELETE \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms/term_custom_field"
```

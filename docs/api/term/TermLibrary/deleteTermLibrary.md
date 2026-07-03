# 删除术语库

```
DELETE /api/v1/knowledge/termLibraries/{libraryId}
```

删除指定术语库。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `libraryId` | string | 术语库 ID。可通过 `listTermLibraries` 接口获取。 |

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
| `404` | 404 | `未查询到术语库「{libraryId}」` | 术语库不存在 |
| `409` | 409 | `术语库「{libraryId}」存在关联术语，无法删除` | 术语库下有术语时拒绝删除 |
| `500` | 500 | `系统错误：{原因}` | 数据库删除失败 |

---

## Example

```bash
curl -X DELETE \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termLibraries/lib_hr"
```

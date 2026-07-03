# 删除术语知识

```
DELETE /api/v1/knowledge/termKnowledges/{knowledgeId}
```

删除指定术语关联知识。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `knowledgeId` | string | 知识 ID。可通过 `listTermKnowledges` 接口获取。 |

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
| `404` | 404 | `未查询到术语知识「{knowledgeId}」` | 知识不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库删除失败 |

---

## Example

```bash
curl -X DELETE \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termKnowledges/kb_001"
```

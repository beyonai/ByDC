# 更新术语知识

```
PUT /api/v1/knowledge/termKnowledges/{knowledgeId}
```

更新术语关联知识。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `knowledgeId` | string | 知识 ID。可通过 `listTermKnowledges` 接口获取。 |

---

## Request Body

```json
{
  "descSummary": "更新后的摘要",
  "desc": "更新后的完整知识内容...",
  "extDocId": "doc_order_v2",
  "sortOrder": 2
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `descSummary` | string | No | 新知识摘要。不传=不修改。 |
| `desc` | string | No | 新知识原文。不传=不修改。 |
| `extSystem` | string | No | 新外部系统编码。不传=不修改。 |
| `extKbId` | string | No | 新外部知识库 ID。不传=不修改。 |
| `extDocId` | string | No | 新外部文档 ID。不传=不修改。 |
| `sortOrder` | integer | No | 新展示排序。不传=不修改。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "knowledgeId": "kb_001",
    "termId": "term_customer",
    "descSummary": "更新后的摘要",
    "desc": "更新后的完整知识内容...",
    "extSystem": null,
    "extKbId": null,
    "extDocId": "doc_order_v2",
    "sortOrder": 2,
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 11:00:00"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到术语知识「{knowledgeId}」` | 知识不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库更新失败 |

---

## Example

```bash
curl -X PUT \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termKnowledges/kb_001" \
  -d '{
    "descSummary": "更新后的客户管理规范",
    "sortOrder": 1
  }'
```

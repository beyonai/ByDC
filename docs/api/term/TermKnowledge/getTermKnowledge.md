# 查询术语知识详情

```
GET /api/v1/knowledge/termKnowledges/{knowledgeId}
```

按 knowledgeId 查询单条知识记录详情。需要 knowledge 服务鉴权。

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
  "message": "查询成功",
  "data": {
    "knowledgeId": "kb_001",
    "termId": "term_customer",
    "descSummary": "客户主数据管理规范",
    "desc": "完整的客户主数据模型定义...",
    "extSystem": null,
    "extKbId": null,
    "extDocId": null,
    "sortOrder": 0,
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.knowledgeId` | string | Yes | 知识 ID。 |
| `data.termId` | string | Yes | 归属术语 ID。 |
| `data.descSummary` | string | No | 知识摘要。 |
| `data.desc` | string | No | 知识原文。 |
| `data.extSystem` | string | No | 外部系统编码。 |
| `data.extKbId` | string | No | 外部知识库 ID。 |
| `data.extDocId` | string | No | 外部文档 ID。 |
| `data.sortOrder` | integer | Yes | 展示排序。 |
| `data.createdTime` | string | Yes | 创建时间。 |
| `data.updatedTime` | string | Yes | 更新时间。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到术语知识「{knowledgeId}」` | 知识不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库查询失败 |

---

## Example

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termKnowledges/kb_001"
```

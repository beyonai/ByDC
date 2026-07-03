# 列出术语知识

```
GET /api/v1/knowledge/termKnowledges
```

分页列出术语关联知识列表。支持按 termId / extSystem 过滤。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `termId` | string | No | — | 归属术语 ID 过滤。 |
| `extSystem` | string | No | — | 外部系统编码过滤。 |
| `pageSize` | integer | No | 20 | 每页条数。上限 100。 |
| `pageToken` | string | No | — | 分页游标。首次请求留空，后续取响应中 `nextPageToken`。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "termKnowledges": [
      {
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
    ],
    "nextPageToken": "...",
    "totalCount": 12
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.termKnowledges[].knowledgeId` | string | Yes | 知识 ID。 |
| `data.termKnowledges[].termId` | string | Yes | 归属术语 ID。 |
| `data.termKnowledges[].descSummary` | string | No | 知识摘要。 |
| `data.termKnowledges[].desc` | string | No | 知识原文。 |
| `data.termKnowledges[].extSystem` | string | No | 外部系统编码。 |
| `data.termKnowledges[].extKbId` | string | No | 外部知识库 ID。 |
| `data.termKnowledges[].extDocId` | string | No | 外部文档 ID。 |
| `data.termKnowledges[].sortOrder` | integer | Yes | 展示排序。 |
| `data.termKnowledges[].createdTime` | string | Yes | 创建时间。 |
| `data.termKnowledges[].updatedTime` | string | Yes | 更新时间。 |
| `data.nextPageToken` | string | No | 下一页游标。 |
| `data.totalCount` | integer | Yes | 全量总数。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `500` | 500 | `系统错误：{原因}` | 数据库查询失败 |

---

## Example

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termKnowledges?termId=term_customer&pageSize=10"
```

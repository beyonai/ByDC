# 列出术语名称

```
GET /api/v1/knowledge/termNames
```

分页列出术语名称（标准名和别名）列表。支持按 termId / nameText 过滤。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `termId` | string | No | — | 归属术语 ID 过滤。 |
| `nameText` | string | No | — | 名称文本精确匹配。 |
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
    "termNames": [
      {
        "nameId": "nm_001",
        "termId": "term_customer",
        "nameText": "客户",
        "isPrimary": true,
        "searchScope": {"scope": "global"},
        "createdTime": "2026-07-02 10:00:00",
        "updatedTime": "2026-07-02 10:00:00"
      }
    ],
    "nextPageToken": "...",
    "totalCount": 8
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.termNames[].nameId` | string | Yes | 名称 ID。 |
| `data.termNames[].termId` | string | Yes | 归属术语 ID。 |
| `data.termNames[].nameText` | string | Yes | 名称文本。 |
| `data.termNames[].isPrimary` | boolean | Yes | 是否标准名称。 |
| `data.termNames[].searchScope` | object | Yes | 搜索作用域。 |
| `data.termNames[].createdTime` | string | Yes | 创建时间。 |
| `data.termNames[].updatedTime` | string | Yes | 更新时间。 |
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
  "https://$HOSTNAME/api/v1/knowledge/termNames?termId=term_customer&pageSize=20"
```

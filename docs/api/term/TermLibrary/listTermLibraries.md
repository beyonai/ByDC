# 列出术语库

```
GET /api/v1/knowledge/termLibraries
```

分页列出术语库列表。支持按 libraryCode / libraryName 过滤。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `libraryCode` | string | No | — | 术语库编码精确匹配。 |
| `libraryName` | string | No | — | 术语库名称模糊匹配。 |
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
    "termLibraries": [
      {
        "libraryId": "lib_hr",
        "libraryCode": "HR_SYSTEM",
        "libraryName": "HR系统术语库",
        "createdTime": "2026-07-02 10:00:00",
        "updatedTime": "2026-07-02 10:00:00"
      }
    ],
    "nextPageToken": "...",
    "totalCount": 3
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.termLibraries[].libraryId` | string | Yes | 术语库 ID。 |
| `data.termLibraries[].libraryCode` | string | Yes | 术语库编码。 |
| `data.termLibraries[].libraryName` | string | Yes | 术语库名称。 |
| `data.termLibraries[].createdTime` | string | Yes | 创建时间。 |
| `data.termLibraries[].updatedTime` | string | Yes | 更新时间。 |
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
  "https://$HOSTNAME/api/v1/knowledge/termLibraries?libraryCode=HR_SYSTEM"
```

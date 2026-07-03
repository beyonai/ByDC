# 查询术语库详情

```
GET /api/v1/knowledge/termLibraries/{libraryId}
```

查询单个术语库的完整详情，含该库下术语总数。需要 knowledge 服务鉴权。

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
  "message": "查询成功",
  "data": {
    "libraryId": "lib_hr",
    "libraryCode": "HR_SYSTEM",
    "libraryName": "HR系统术语库",
    "termCount": 152,
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.termCount` | integer | Yes | 该术语库下术语总数。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到术语库「{libraryId}」` | 术语库不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库查询失败 |

---

## Example

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termLibraries/lib_hr"
```

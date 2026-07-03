# 更新术语库

```
PUT /api/v1/knowledge/termLibraries/{libraryId}
```

更新术语库元信息。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `libraryId` | string | 术语库 ID。可通过 `listTermLibraries` 接口获取。 |

---

## Request Body

```json
{
  "libraryName": "HR系统术语库V2"
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `libraryName` | string | No | 新的术语库名称。不传=不修改。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "libraryId": "lib_hr",
    "libraryCode": "HR_SYSTEM",
    "libraryName": "HR系统术语库V2",
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 11:00:00"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到术语库「{libraryId}」` | 术语库不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库更新失败 |

---

## Example

```bash
curl -X PUT \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termLibraries/lib_hr" \
  -d '{"libraryName": "HR系统术语库V2"}'
```

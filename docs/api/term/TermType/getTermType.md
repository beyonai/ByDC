# 查询术语类型详情

```
GET /api/v1/knowledge/termTypes/{typeCode}
```

按 typeCode 查询单个术语类型详情，含该类型下术语总数。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `typeCode` | string | 类型编码。可通过 `listTermTypes` 接口获取。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "typeId": 1,
    "typeCode": "view",
    "typeName": "视图",
    "typeDesc": "数据视图类型",
    "typeCategory": 1,
    "isBuiltin": true,
    "termCount": 320,
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.termCount` | integer | Yes | 该类型下术语总数。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到术语类型「{typeCode}」` | 类型不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库查询失败 |

---

## Example

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termTypes/object"
```

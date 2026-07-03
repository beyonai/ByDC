# 查询术语名称详情

```
GET /api/v1/knowledge/termNames/{nameId}
```

按 nameId 查询单个名称记录详情。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `nameId` | string | 名称 ID。可通过 `listTermNames` 接口获取。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "nameId": "nm_001",
    "termId": "term_customer",
    "nameText": "客户",
    "isPrimary": true,
    "searchScope": {"scope": "global"},
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.nameId` | string | Yes | 名称 ID。 |
| `data.termId` | string | Yes | 归属术语 ID。 |
| `data.nameText` | string | Yes | 名称文本。 |
| `data.isPrimary` | boolean | Yes | 是否标准名称。 |
| `data.searchScope` | object | Yes | 搜索作用域。 |
| `data.createdTime` | string | Yes | 创建时间。 |
| `data.updatedTime` | string | Yes | 更新时间。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到术语名称「{nameId}」` | 名称不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库查询失败 |

---

## Example

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termNames/nm_001"
```

# 更新术语名称

```
PUT /api/v1/knowledge/termNames/{nameId}
```

更新术语名称的作用域和文本。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `nameId` | string | 名称 ID。可通过 `listTermNames` 接口获取。 |

---

## Request Body

```json
{
  "nameText": "企业客户",
  "searchScope": {"scope": "object", "code": "obj_crm_view"}
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `nameText` | string | No | 新名称文本。不传=不修改。 |
| `searchScope` | object | No | 新搜索作用域（完全替换）。不传=不修改。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "nameId": "nm_002",
    "termId": "term_customer",
    "nameText": "企业客户",
    "isPrimary": false,
    "searchScope": {"scope": "object", "code": "obj_crm_view"},
    "createdTime": "2026-07-02 10:05:00",
    "updatedTime": "2026-07-02 11:00:00"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到术语名称「{nameId}」` | 名称不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库更新失败 |

---

## Example

```bash
curl -X PUT \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termNames/nm_002" \
  -d '{"nameText": "企业客户"}'
```

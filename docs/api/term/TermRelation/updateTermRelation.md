# 更新术语关系

```
PUT /api/v1/knowledge/termRelations/{relationId}
```

更新术语关系属性。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `relationId` | string | 关系 ID。可通过 `listTermRelations` 接口获取。 |

---

## Request Body

```json
{
  "relationName": "OWNS_ORDER",
  "relationCategory": "BUSINESS",
  "cardinality": "N:N",
  "extAttrs": {"updated": true}
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `relationName` | string | No | 新关系名称。不传=不修改。 |
| `relationCategory` | string | No | 新关系类别。不传=不修改。 |
| `cardinality` | string | No | 新数量约束。不传=不修改。 |
| `extAttrs` | object | No | 新扩展属性（完全替换）。不传=不修改。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "relationId": "rel_001",
    "sourceTermId": "term_customer",
    "targetTermId": "term_order",
    "relationName": "OWNS_ORDER",
    "relationCategory": "BUSINESS",
    "cardinality": "N:N",
    "extAttrs": {"updated": true},
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 11:00:00"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到术语关系「{relationId}」` | 关系不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库更新失败 |

---

## Example

```bash
curl -X PUT \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termRelations/rel_001" \
  -d '{"cardinality": "N:N"}'
```

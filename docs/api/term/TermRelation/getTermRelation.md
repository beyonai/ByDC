# 查询术语关系详情

```
GET /api/v1/knowledge/termRelations/{relationId}
```

按 relationId 查询单个关系详情。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `relationId` | string | 关系 ID。可通过 `listTermRelations` 接口获取。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "relationId": "rel_001",
    "sourceTermId": "term_customer",
    "sourceTermName": "客户",
    "targetTermId": "term_order",
    "targetTermName": "订单",
    "relationName": "HAS_ORDER",
    "relationCategory": "BUSINESS",
    "cardinality": "1:N",
    "extAttrs": {},
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.relationId` | string | Yes | 关系 ID。 |
| `data.sourceTermId` | string | Yes | 源术语 ID。 |
| `data.sourceTermName` | string | Yes | 源术语标准名称。 |
| `data.targetTermId` | string | Yes | 目标术语 ID。 |
| `data.targetTermName` | string | Yes | 目标术语标准名称。 |
| `data.relationName` | string | Yes | 关系名称。 |
| `data.relationCategory` | string | Yes | 关系类别。 |
| `data.cardinality` | string | No | 数量约束。 |
| `data.extAttrs` | object | Yes | 扩展属性。 |
| `data.createdTime` | string | Yes | 创建时间。 |
| `data.updatedTime` | string | Yes | 更新时间。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到术语关系「{relationId}」` | 关系不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库查询失败 |

---

## Example

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termRelations/rel_001"
```

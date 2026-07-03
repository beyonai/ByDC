# 列出术语关系

```
GET /api/v1/knowledge/termRelations
```

分页列出术语关系列表。支持按 sourceTermId / targetTermId / relationCategory / cardinality 过滤。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `sourceTermId` | string | No | — | 源术语 ID 过滤。 |
| `targetTermId` | string | No | — | 目标术语 ID 过滤。 |
| `relationCategory` | string | No | — | 关系类别过滤。 |
| `cardinality` | string | No | — | 基数约束过滤。 |
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
    "termRelations": [
      {
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
    ],
    "nextPageToken": "...",
    "totalCount": 45
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.termRelations[].relationId` | string | Yes | 关系 ID。 |
| `data.termRelations[].sourceTermId` | string | Yes | 源术语 ID。 |
| `data.termRelations[].sourceTermName` | string | Yes | 源术语标准名称。 |
| `data.termRelations[].targetTermId` | string | Yes | 目标术语 ID。 |
| `data.termRelations[].targetTermName` | string | Yes | 目标术语标准名称。 |
| `data.termRelations[].relationName` | string | Yes | 关系名称。 |
| `data.termRelations[].relationCategory` | string | Yes | 关系类别。 |
| `data.termRelations[].cardinality` | string | No | 数量约束。 |
| `data.termRelations[].extAttrs` | object | Yes | 扩展属性。 |
| `data.termRelations[].createdTime` | string | Yes | 创建时间。 |
| `data.termRelations[].updatedTime` | string | Yes | 更新时间。 |
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
  "https://$HOSTNAME/api/v1/knowledge/termRelations?sourceTermId=term_customer&pageSize=10"
```

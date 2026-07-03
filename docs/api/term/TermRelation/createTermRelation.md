# 创建术语关系

```
POST /api/v1/knowledge/termRelations
```

创建两个术语之间的关系。`(sourceTermId, targetTermId, relationName)` 三者组合唯一。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Request Body

```json
{
  "relationId": "rel_has_order",     // string，可选。关系 ID，不传则自动生成
  "sourceTermId": "term_customer",   // string，必填。源术语 ID
  "targetTermId": "term_order",      // string，必填。目标术语 ID
  "relationName": "HAS_ORDER",       // string，必填。关系名称
  "relationCategory": "BUSINESS",    // string，可选。关系类别，默认 "BUSINESS"
  "cardinality": "1:N",             // string，可选。数量约束
  "extAttrs": {}                     // object，可选。扩展属性
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `relationId` | string | No | 关系 ID。不传时服务端雪花算法自动生成。 |
| `sourceTermId` | string | Yes | 源术语 ID，必须存在于 `term` 表。 |
| `targetTermId` | string | Yes | 目标术语 ID，必须存在于 `term` 表。 |
| `relationName` | string | Yes | 关系名称。最长 255 字符。 |
| `relationCategory` | string | No | 关系类别。常见值：`"BUSINESS"`、`"HAS_FIELD"`、`"HAS_TERM"`。默认 `"BUSINESS"`。 |
| `cardinality` | string | No | 数量约束：`"1:1"`、`"1:N"`、`"N:1"`、`"N:N"`。 |
| `extAttrs` | object | No | 扩展属性（JSONB）。默认 `{}`。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "relationId": "rel_has_order",
    "sourceTermId": "term_customer",
    "targetTermId": "term_order",
    "relationName": "HAS_ORDER",
    "relationCategory": "BUSINESS",
    "cardinality": "1:N",
    "extAttrs": {},
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `sourceTermId`、`targetTermId`、`relationName` 任一缺失；源或目标术语不存在 |
| `409` | 409 | `术语关系「来源→目标 关系名」已存在` | 同源、同目标、同关系名的关系已存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库写入失败 |

---

## Example

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termRelations" \
  -d '{
    "sourceTermId": "term_customer",
    "targetTermId": "term_order",
    "relationName": "HAS_ORDER",
    "relationCategory": "BUSINESS",
    "cardinality": "1:N"
  }'
```

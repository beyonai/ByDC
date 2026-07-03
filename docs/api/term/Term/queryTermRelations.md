# 查询术语关系

```
GET /api/v1/knowledge/terms/{termId}/relations
```

查询指定术语的所有关联关系（作为源或目标的进出边），支持按关系类别、基数过滤，支撑血缘分析和影响范围分析。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `termId` | string | 术语 ID，即 `term.term_id`。可通过 `searchTerms` 接口获取。 |

---

## Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `direction` | string | No | `both` | 关系方向：`source` 仅查出边（该术语为源）、`target` 仅查入边（该术语为目标）、`both` 双向查询。 |
| `relationCategory` | string | No | — | 关系类别过滤，如 `"BUSINESS"`、`"HAS_FIELD"`、`"HAS_TERM"`。不传 = 不限类别。 |
| `cardinality` | string | No | — | 基数约束过滤：`"1:1"`、`"1:N"`、`"N:1"`、`"N:N"`。不传 = 不限。 |
| `pageSize` | integer | No | 20 | 每页条数。上限 100。 |
| `pageToken` | string | No | — | 分页游标。首次请求留空，后续取响应中 `nextPageToken`。 |

---

## Request Body

无。

---

## Response Body

```
QueryTermRelationsResponse
```

### Schema

```json
{
  "code": 200,                       // integer
  "success": true,                   // boolean
  "message": "查询成功",              // string
  "data": {                          // object，失败时为 null
    "termId": "term_customer",       // string。查询的术语 ID
    "outgoing": [                    // object[]，可选。出边关系列表（该术语为 source）
      {
        "relationId": "rel_001",     // string。关系唯一 ID
        "sourceTermId": "term_customer",  // string。源术语 ID
        "targetTermId": "term_order",     // string。目标术语 ID
        "targetTermName": "订单",          // string。目标术语标准名称
        "targetTermTypeCode": "object",   // string。目标术语类型编码
        "relationName": "HAS_ORDER",      // string。关系名称
        "relationCategory": "BUSINESS",   // string。关系类别
        "cardinality": "1:N",             // string，可选。数量约束
        "extAttrs": {},                   // object。自定义扩展属性
        "createdTime": "2026-03-10 09:00:00",  // string。创建时间
        "updatedTime": "2026-03-10 09:00:00"   // string。更新时间
      }
    ],
    "incoming": [                    // object[]，可选。入边关系列表（该术语为 target）
      {
        "relationId": "rel_005",
        "sourceTermId": "term_biz_root",
        "sourceTermName": "业务对象",
        "sourceTermTypeCode": "object",
        "targetTermId": "term_customer",
        "relationName": "SUBCLASS_OF",
        "relationCategory": "BUSINESS",
        "cardinality": "1:1",
        "extAttrs": {},
        "createdTime": "2026-01-15 10:00:00",
        "updatedTime": "2026-01-15 10:00:00"
      }
    ],
    "nextPageToken": "...",          // string，可选。下一页游标
    "totalCount": 8                  // integer。关系总数（outgoing + incoming）
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | object | Yes | 业务数据。失败时为 `null`。 |
| `data.termId` | string | Yes | 查询的目标术语 ID，用于确认回显。 |
| `data.outgoing` | object[] | No | 出边关系列表。该术语作为关系源（`source_term_id = termId`）的所有关系。`direction = target` 时省略。 |
| `data.incoming` | object[] | No | 入边关系列表。该术语作为关系目标（`target_term_id = termId`）的所有关系。`direction = source` 时省略。 |
| `data.outgoing[].relationId` | string | Yes | 关系唯一 ID。 |
| `data.outgoing[].sourceTermId` | string | Yes | 源术语 ID。 |
| `data.outgoing[].targetTermId` | string | Yes | 目标术语 ID。 |
| `data.outgoing[].targetTermName` | string | Yes | 目标术语标准名称。 |
| `data.outgoing[].targetTermTypeCode` | string | Yes | 目标术语类型编码。 |
| `data.incoming[].sourceTermName` | string | Yes | 源术语标准名称（仅 incoming）。 |
| `data.incoming[].sourceTermTypeCode` | string | Yes | 源术语类型编码（仅 incoming）。 |
| `data.incoming[].targetTermId` | string | Yes | 目标术语 ID（即查询的 `termId`）。 |
| `data.*.relationName` | string | Yes | 关系名称。 |
| `data.*.relationCategory` | string | Yes | 关系类别。常见值：`"BUSINESS"`（业务关系）、`"HAS_FIELD"`（对象拥有字段）、`"HAS_TERM"`（属性拥有值）、`"SUBCLASS_OF"`（父子继承）。 |
| `data.*.cardinality` | string | No | 数量约束：`"1:1"`、`"1:N"`、`"N:1"`、`"N:N"`。 |
| `data.*.extAttrs` | object | Yes | 自定义扩展属性（JSONB）。 |
| `data.*.createdTime` | string | Yes | 创建时间。格式 `YYYY-MM-DD HH:mm:ss`。 |
| `data.*.updatedTime` | string | Yes | 更新时间。格式 `YYYY-MM-DD HH:mm:ss`。 |
| `data.nextPageToken` | string | No | 下一页游标。最后一页无此字段。 |
| `data.totalCount` | integer | Yes | 关系总数（`outgoing` + `incoming` 去重总数）。 |

### 字段说明

> `outgoing` / `incoming` 的字段差异：outgoing 中 `sourceTermId` 恒等于查询的 `termId`，聚焦展示 `targetTermName` 和 `targetTermTypeCode`；incoming 中 `targetTermId` 恒等于查询的 `termId`，聚焦展示 `sourceTermName` 和 `sourceTermTypeCode`。
>
> 关系类别 `relationCategory` 枚举值由 `term_relation` 表的数据决定，非系统内置枚举。常见业务约定：`"BUSINESS"` — 业务语义关系；`"HAS_FIELD"` — 对象到属性的关系；`"HAS_TERM"` — 属性到枚举值的关系。

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `termId` 缺失、`direction` 不在枚举范围内、`pageSize` 超出上限 |
| `404` | 404 | `未查询到术语「{termId}」` | 指定术语不存在（但允许无关系记录时返回空列表） |
| `500` | 500 | `系统错误：{原因}` | 数据库连接失败 |

### Error Example

```json
{
  "code": 400,
  "success": false,
  "message": "参数错误：direction 仅支持 source / target / both",
  "data": null
}
```

---

## Example

### 查询术语的完整关系图

查所有进出边，不限制 category 和 cardinality。

#### Request

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms/term_customer/relations?direction=both&pageSize=20"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "termId": "term_customer",
    "outgoing": [
      {
        "relationId": "rel_001",
        "sourceTermId": "term_customer",
        "targetTermId": "term_order",
        "targetTermName": "订单",
        "targetTermTypeCode": "object",
        "relationName": "HAS_ORDER",
        "relationCategory": "BUSINESS",
        "cardinality": "1:N",
        "extAttrs": {},
        "createdTime": "2026-03-10 09:00:00",
        "updatedTime": "2026-03-10 09:00:00"
      },
      {
        "relationId": "rel_002",
        "sourceTermId": "term_customer",
        "targetTermId": "prop_customer_name",
        "targetTermName": "客户名称",
        "targetTermTypeCode": "prop",
        "relationName": "HAS_FIELD",
        "relationCategory": "HAS_FIELD",
        "cardinality": "1:N",
        "extAttrs": {},
        "createdTime": "2026-01-15 10:00:00",
        "updatedTime": "2026-01-15 10:00:00"
      }
    ],
    "incoming": [
      {
        "relationId": "rel_003",
        "sourceTermId": "term_biz_root",
        "sourceTermName": "业务对象",
        "sourceTermTypeCode": "object",
        "targetTermId": "term_customer",
        "relationName": "SUBCLASS_OF",
        "relationCategory": "BUSINESS",
        "cardinality": "1:1",
        "extAttrs": {},
        "createdTime": "2026-01-15 10:00:00",
        "updatedTime": "2026-01-15 10:00:00"
      }
    ],
    "totalCount": 3
  }
}
```

### 仅查询业务关系

只查出边中类别为 `BUSINESS` 的关系，用于分析某个业务对象与哪些其他对象关联。

#### Request

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/terms/term_customer/relations?direction=source&relationCategory=BUSINESS&pageSize=10"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "termId": "term_customer",
    "outgoing": [
      {
        "relationId": "rel_001",
        "sourceTermId": "term_customer",
        "targetTermId": "term_order",
        "targetTermName": "订单",
        "targetTermTypeCode": "object",
        "relationName": "HAS_ORDER",
        "relationCategory": "BUSINESS",
        "cardinality": "1:N",
        "extAttrs": {},
        "createdTime": "2026-03-10 09:00:00",
        "updatedTime": "2026-03-10 09:00:00"
      },
      {
        "relationId": "rel_004",
        "sourceTermId": "term_customer",
        "targetTermId": "term_contract",
        "targetTermName": "合同",
        "targetTermTypeCode": "object",
        "relationName": "SIGNS",
        "relationCategory": "BUSINESS",
        "cardinality": "1:N",
        "extAttrs": {},
        "createdTime": "2026-03-15 11:00:00",
        "updatedTime": "2026-03-15 11:00:00"
      }
    ],
    "totalCount": 2
  }
}
```

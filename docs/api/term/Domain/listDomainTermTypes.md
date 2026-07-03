# 查询领域下的术语类型

```
GET /api/v1/knowledge/domains/{domainId}/termTypes
```

查询指定领域下关联的所有术语类型。通过 `domain_term_type` 关联表获取，含各类型在该领域下的术语数量。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `domainId` | string | 领域 ID。可通过 `listDomains` 接口获取。 |

---

## Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `pageSize` | integer | No | 20 | 每页条数。上限 100。 |
| `pageToken` | string | No | — | 分页游标。首次请求留空，后续取响应中 `nextPageToken`。 |

---

## Request Body

无。

---

## Response Body

```
ListDomainTermTypesResponse
```

### Schema

```json
{
  "code": 200,                       // integer
  "success": true,                   // boolean
  "message": "查询成功",              // string
  "data": {                          // object，失败时为 null
    "termTypes": [                   // object[]
      {
        "typeCode": "object",        // string。术语类型编码
        "typeName": "业务对象",        // string。术语类型名称
        "termCount": 45              // integer。该领域该类型下的术语总数
      },
      {
        "typeCode": "prop",
        "typeName": "属性",
        "termCount": 107
      }
    ],
    "nextPageToken": "...",          // string，可选。下一页游标
    "totalCount": 2                  // integer。全量类型数
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
| `data.termTypes` | object[] | Yes | 该领域关联的术语类型列表。 |
| `data.termTypes[].typeCode` | string | Yes | 术语类型编码。 |
| `data.termTypes[].typeName` | string | Yes | 术语类型名称。 |
| `data.termTypes[].termCount` | integer | Yes | 该领域该类型下的术语总数。 |
| `data.nextPageToken` | string | No | 下一页游标。最后一页无此字段。 |
| `data.totalCount` | integer | Yes | 全量类型总数。 |

### 字段说明

> 内部通过 `domain_term_type` 关联表 JOIN `term_type`，`termCount` 统计该领域该类型下术语数（`COUNT(*) FROM term WHERE domain_ids @> ARRAY[?] AND term_type_code = ?`）。无术语记录的类型不会出现在关联结果中，除非 `domain_term_type` 主动注册。

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `domainId` 缺失 |
| `404` | 404 | `未查询到领域「{domainId}」` | 领域不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库查询失败 |

---

## Example

### 查询领域下的术语类型

#### Request

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/domains/domain_crm/termTypes"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "termTypes": [
      {"typeCode": "object", "typeName": "业务对象", "termCount": 45},
      {"typeCode": "prop", "typeName": "属性", "termCount": 107}
    ],
    "totalCount": 2
  }
}
```

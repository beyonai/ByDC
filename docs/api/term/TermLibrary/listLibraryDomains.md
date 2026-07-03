# 查询术语库覆盖的领域

```
GET /api/v1/knowledge/termLibraries/{libraryId}/domains
```

查询指定术语库下所有关联的领域。通过 `domain_library` 关联表获取，去重后返回，含该术语库下各领域的术语数量。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `libraryId` | string | 术语库 ID。可通过 `listTermLibraries` 接口获取。 |

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
ListLibraryDomainsResponse
```

### Schema

```json
{
  "code": 200,                       // integer
  "success": true,                   // boolean
  "message": "查询成功",              // string
  "data": {                          // object，失败时为 null
    "domains": [                     // object[]
      {
        "domainId": "domain_crm",    // string。领域 ID
        "domainName": "客户管理",      // string。领域名称
        "domainDesc": "CRM 相关术语分类",  // string，可选。领域描述
        "termCount": 152             // integer。该领域在该术语库下的术语数
      },
      {
        "domainId": "domain_order",
        "domainName": "订单管理",
        "domainDesc": "订单相关术语",
        "termCount": 89
      }
    ],
    "nextPageToken": "...",          // string，可选。下一页游标
    "totalCount": 5                  // integer。全量领域数
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
| `data.domains` | object[] | Yes | 该术语库覆盖的领域列表。 |
| `data.domains[].domainId` | string | Yes | 领域 ID。 |
| `data.domains[].domainName` | string | Yes | 领域名称。 |
| `data.domains[].domainDesc` | string | No | 领域描述。 |
| `data.domains[].termCount` | integer | Yes | 该领域在该术语库下的术语总数。 |
| `data.nextPageToken` | string | No | 下一页游标。最后一页无此字段。 |
| `data.totalCount` | integer | Yes | 全量领域总数。 |

### 字段说明

> 内部通过 `domain_library` 关联表 JOIN `domain`，`termCount` 统计该术语库下属于该领域的术语总数（`COUNT(*) FROM term WHERE library_id = ? AND domain_ids @> ARRAY[?]`）。

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `libraryId` 缺失 |
| `404` | 404 | `未查询到术语库「{libraryId}」` | 术语库不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库查询失败 |

---

## Example

### 查询术语库下所有领域

#### Request

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termLibraries/lib_hr/domains?pageSize=10"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "domains": [
      {
        "domainId": "domain_hr",
        "domainName": "人力资源",
        "domainDesc": "HR 相关术语分类",
        "termCount": 152
      },
      {
        "domainId": "domain_org",
        "domainName": "组织架构",
        "domainDesc": "部门、岗位等组织相关术语",
        "termCount": 73
      }
    ],
    "totalCount": 2
  }
}
```

### 术语库无术语

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "domains": [],
    "totalCount": 0
  }
}
```

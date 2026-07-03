# 列出领域

```
GET /api/v1/knowledge/domains
```

分页列出领域列表。支持按 `parentId` 过滤子领域，实现无限层级树形遍历。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `parentId` | string | No | — | 父领域 ID 过滤。传 `"__root__"` 查询根节点（`parentId IS NULL`）。 |
| `domainName` | string | No | — | 领域名称模糊匹配。 |
| `pageSize` | integer | No | 20 | 每页条数。上限 100。 |
| `pageToken` | string | No | — | 分页游标。首次请求留空，后续取响应中 `nextPageToken`。 |

---

## Request Body

无。

---

## Response Body

```
ListDomainsResponse
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
        "parentId": null,            // string，可选。父领域 ID
        "domainDesc": "CRM 相关术语分类",  // string，可选。领域描述
        "libraryIds": ["lib_crm"],   // string[]。归属术语库 ID 列表
        "termTypeCodes": ["object", "prop"],  // string[]。领域下可用术语类型编码
        "termCount": 152,            // integer。该领域下术语总数
        "createdTime": "2026-07-02 10:00:00",  // string。创建时间
        "updatedTime": "2026-07-02 10:00:00"   // string。更新时间
      }
    ],
    "nextPageToken": "...",          // string，可选。下一页游标
    "totalCount": 5                  // integer。全量总数
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
| `data.domains` | object[] | Yes | 当前页领域列表。 |
| `data.domains[].domainId` | string | Yes | 领域 ID。 |
| `data.domains[].domainName` | string | Yes | 领域名称。 |
| `data.domains[].parentId` | string | No | 父领域 ID，根节点为 `null`。 |
| `data.domains[].domainDesc` | string | No | 领域描述。 |
| `data.domains[].libraryIds` | string[] | Yes | 归属术语库 ID 列表。 |
| `data.domains[].termTypeCodes` | string[] | Yes | 领域下可用术语类型编码列表。 |
| `data.domains[].termCount` | integer | No | 该领域下术语总数。 |
| `data.domains[].createdTime` | string | Yes | 创建时间。格式 `YYYY-MM-DD HH:mm:ss`。 |
| `data.domains[].updatedTime` | string | Yes | 更新时间。格式 `YYYY-MM-DD HH:mm:ss`。 |
| `data.nextPageToken` | string | No | 下一页游标。最后一页无此字段。 |
| `data.totalCount` | integer | Yes | 全量总数。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `500` | 500 | `系统错误：{原因}` | 数据库查询失败 |

---

## Example

### 查询所有根领域

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/domains?parentId=__root__&pageSize=10"
```

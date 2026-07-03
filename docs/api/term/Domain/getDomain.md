# 查询领域详情

```
GET /api/v1/knowledge/domains/{domainId}
```

查询单个领域的完整详情，包含关联的术语库、术语类型及各自的术语数量。需要 knowledge 服务鉴权。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `domainId` | string | 领域 ID。可通过 `listDomains` 接口获取。 |

---

## Query Parameters

无。

---

## Request Body

无。

---

## Response Body

```
GetDomainResponse
```

### Schema

```json
{
  "code": 200,                         // integer
  "success": true,                     // boolean
  "message": "查询成功",                // string
  "data": {                            // object，失败时为 null
    "domainId": "domain_crm",          // string。领域 ID
    "domainName": "客户管理",            // string。领域名称
    "parentId": null,                  // string，可选。父领域 ID
    "parentDomainName": null,          // string，可选。父领域名称
    "domainDesc": "CRM 相关术语分类",    // string，可选。领域描述
    "libraryIds": ["lib_crm"],         // string[]。归属术语库 ID 列表
    "termTypeCodes": ["object", "prop"], // string[]。领域下可用术语类型编码
    "libraries": [                     // object[]。关联术语库详情
      {"libraryId": "lib_crm", "libraryName": "CRM系统术语库"}
    ],
    "termTypes": [                     // object[]。关联术语类型详情
      {"typeCode": "object", "typeName": "业务对象", "termCount": 45},
      {"typeCode": "prop", "typeName": "属性", "termCount": 107}
    ],
    "childrenCount": 3,                // integer。子领域数量
    "createdTime": "2026-07-02 10:00:00",  // string。创建时间
    "updatedTime": "2026-07-02 10:00:00"   // string。更新时间
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
| `data.domainId` | string | Yes | 领域 ID。 |
| `data.domainName` | string | Yes | 领域名称。 |
| `data.parentId` | string | No | 父领域 ID，根节点为 `null`。 |
| `data.parentDomainName` | string | No | 父领域名称，根节点为 `null`。 |
| `data.domainDesc` | string | No | 领域描述。 |
| `data.libraryIds` | string[] | Yes | 归属术语库 ID 列表。 |
| `data.termTypeCodes` | string[] | Yes | 领域下可用术语类型编码列表。 |
| `data.libraries` | object[] | Yes | 关联术语库详情。 |
| `data.libraries[].libraryId` | string | Yes | 术语库 ID。 |
| `data.libraries[].libraryName` | string | Yes | 术语库名称。 |
| `data.termTypes` | object[] | Yes | 关联术语类型详情。 |
| `data.termTypes[].typeCode` | string | Yes | 术语类型编码。 |
| `data.termTypes[].typeName` | string | Yes | 术语类型名称。 |
| `data.termTypes[].termCount` | integer | Yes | 该领域该类型下的术语总数。 |
| `data.childrenCount` | integer | No | 子领域数量。 |
| `data.createdTime` | string | Yes | 创建时间。格式 `YYYY-MM-DD HH:mm:ss`。 |
| `data.updatedTime` | string | Yes | 更新时间。格式 `YYYY-MM-DD HH:mm:ss`。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `404` | 404 | `未查询到领域「{domainId}」` | 指定领域不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库查询失败 |

---

## Example

### 查询单个领域完整详情

```bash
curl -X GET \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/domains/domain_crm"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": {
    "domainId": "domain_crm",
    "domainName": "客户管理",
    "parentId": null,
    "parentDomainName": null,
    "domainDesc": "CRM 相关术语分类",
    "libraryIds": ["lib_crm"],
    "termTypeCodes": ["object", "prop"],
    "libraries": [
      {"libraryId": "lib_crm", "libraryName": "CRM系统术语库"}
    ],
    "termTypes": [
      {"typeCode": "object", "typeName": "业务对象", "termCount": 45},
      {"typeCode": "prop", "typeName": "属性", "termCount": 107}
    ],
    "childrenCount": 3,
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

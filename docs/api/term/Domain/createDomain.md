# 创建领域

```
POST /api/v1/knowledge/domains
```

创建新的术语分类领域，同时关联归属的术语库和术语类型。domainId 可选，不传时服务端雪花算法自动生成。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Query Parameters

无。

---

## Request Body

```
CreateDomainRequest
```

### Schema

```json
{
  "domainId": "domain_crm",           // string，可选。领域 ID，不传则自动生成
  "domainName": "客户管理",             // string，必填。领域名称
  "parentId": "domain_root",          // string，可选。父领域 ID，根节点为 null
  "domainDesc": "CRM 相关术语分类",     // string，可选。领域描述
  "libraryIds": ["lib_crm", "lib_hr"],// string[]，可选。归属术语库 ID 列表
  "termTypeCodes": ["object", "prop"] // string[]，可选。领域下可用术语类型编码
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `domainId` | string | No | 领域 ID。不传时服务端雪花算法自动生成。 |
| `domainName` | string | Yes | 领域名称，最长 255 字符。 |
| `parentId` | string | No | 父领域 ID。不传 = 根节点。 |
| `domainDesc` | string | No | 领域描述。 |
| `libraryIds` | string[] | No | 归属术语库 ID 列表。不传 = 不关联任何库。传入的 libraryId 必须存在。 |
| `termTypeCodes` | string[] | No | 领域下可用的术语类型编码列表。不传 = 不限类型。传入的 typeCode 必须存在。 |

---

## Response Body

```
CreateDomainResponse
```

### Schema

```json
{
  "code": 200,                         // integer
  "success": true,                     // boolean
  "message": "创建成功",                // string
  "data": {                            // object，失败时为 null
    "domainId": "domain_crm",          // string。领域 ID
    "domainName": "客户管理",            // string。领域名称
    "parentId": null,                  // string，可选。父领域 ID
    "domainDesc": "CRM 相关术语分类",    // string，可选。领域描述
    "libraryIds": ["lib_crm"],         // string[]。归属术语库 ID 列表
    "termTypeCodes": ["object", "prop"], // string[]。领域下可用术语类型编码
    "libraries": [                     // object[]。术语库详情
      {
        "libraryId": "lib_crm",
        "libraryName": "CRM系统术语库"
      }
    ],
    "termTypes": [                     // object[]。术语类型详情
      {
        "typeCode": "object",
        "typeName": "业务对象"
      },
      {
        "typeCode": "prop",
        "typeName": "属性"
      }
    ],
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
| `data` | object | Yes | 创建后的领域对象。失败时为 `null`。 |
| `data.domainId` | string | Yes | 领域 ID，主键。 |
| `data.domainName` | string | Yes | 领域名称。 |
| `data.parentId` | string | No | 父领域 ID，根节点为 `null`。 |
| `data.domainDesc` | string | No | 领域描述。 |
| `data.libraryIds` | string[] | Yes | 归属术语库 ID 列表。 |
| `data.termTypeCodes` | string[] | Yes | 领域下可用术语类型编码列表。 |
| `data.libraries` | object[] | Yes | 术语库详情（回显）。 |
| `data.libraries[].libraryId` | string | Yes | 术语库 ID。 |
| `data.libraries[].libraryName` | string | Yes | 术语库名称。 |
| `data.termTypes` | object[] | Yes | 术语类型详情（回显）。 |
| `data.termTypes[].typeCode` | string | Yes | 术语类型编码。 |
| `data.termTypes[].typeName` | string | Yes | 术语类型名称。 |
| `data.createdTime` | string | Yes | 创建时间。格式 `YYYY-MM-DD HH:mm:ss`。 |
| `data.updatedTime` | string | Yes | 更新时间。格式 `YYYY-MM-DD HH:mm:ss`。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `domainName` 缺失或为空；`parentId` 指定的父领域不存在；`libraryIds` 中存在不存在的术语库 ID；`termTypeCodes` 中存在不存在的类型编码 |
| `409` | 409 | `领域「{domainId}」已存在` | `domainId` 与已有领域冲突 |
| `500` | 500 | `系统错误：{原因}` | 数据库写入失败 |

### Error Example

```json
{
  "code": 409,
  "success": false,
  "message": "领域「domain_crm」已存在",
  "data": null
}
```

---

## Example

### 创建领域并关联术语库和类型

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/domains" \
  -d '{
    "domainName": "客户管理",
    "domainDesc": "CRM 相关术语分类",
    "libraryIds": ["lib_crm"],
    "termTypeCodes": ["object", "prop"]
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "domainId": "domain_crm",
    "domainName": "客户管理",
    "parentId": null,
    "domainDesc": "CRM 相关术语分类",
    "libraryIds": ["lib_crm"],
    "termTypeCodes": ["object", "prop"],
    "libraries": [
      {"libraryId": "lib_crm", "libraryName": "CRM系统术语库"}
    ],
    "termTypes": [
      {"typeCode": "object", "typeName": "业务对象"},
      {"typeCode": "prop", "typeName": "属性"}
    ],
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

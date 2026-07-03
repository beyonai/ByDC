# 更新领域

```
PUT /api/v1/knowledge/domains/{domainId}
```

更新领域元信息及关联的术语库、术语类型。所有字段可选，仅更新传入的非空字段。`libraryIds` / `termTypeCodes` 传入时**全量替换**原有关联，不传不修改。需要 knowledge 服务鉴权。

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

```
UpdateDomainRequest
```

### Schema

```json
{
  "domainName": "客户关系管理",          // string，可选。新名称
  "parentId": "domain_biz",           // string，可选。新父领域 ID
  "domainDesc": "更新后的描述",         // string，可选。新描述
  "libraryIds": ["lib_crm", "lib_hr"],// string[]，可选。新术语库列表（全量替换）
  "termTypeCodes": ["object"]          // string[]，可选。新术语类型列表（全量替换）
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `domainName` | string | No | 新的领域名称。不传 = 不修改。 |
| `parentId` | string | No | 新的父领域 ID。不传 = 不修改。传 `""` = 移至根节点。 |
| `domainDesc` | string | No | 新的领域描述。不传 = 不修改。 |
| `libraryIds` | string[] | No | 新的术语库 ID 列表。传入时**全量替换**原有关联，传 `[]` 清空。不传 = 不修改。 |
| `termTypeCodes` | string[] | No | 新的术语类型编码列表。传入时**全量替换**原有关联，传 `[]` 清空。不传 = 不修改。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功",
  "data": {
    "domainId": "domain_crm",
    "domainName": "客户关系管理",
    "parentId": null,
    "domainDesc": "更新后的描述",
    "libraryIds": ["lib_crm", "lib_hr"],
    "termTypeCodes": ["object"],
    "libraries": [
      {"libraryId": "lib_crm", "libraryName": "CRM系统术语库"},
      {"libraryId": "lib_hr", "libraryName": "HR系统术语库"}
    ],
    "termTypes": [
      {"typeCode": "object", "typeName": "业务对象"}
    ],
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 11:00:00"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data.libraryIds` | string[] | Yes | 更新后的归属术语库 ID 列表。 |
| `data.termTypeCodes` | string[] | Yes | 更新后的术语类型编码列表。 |
| `data.libraries` | object[] | Yes | 关联术语库详情（回显）。 |
| `data.termTypes` | object[] | Yes | 关联术语类型详情（回显）。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `parentId` 指定的父领域不存在；`libraryIds` 中存在不存在的术语库；`termTypeCodes` 中存在不存在的类型 |
| `404` | 404 | `未查询到领域「{domainId}」` | 领域不存在 |
| `500` | 500 | `系统错误：{原因}` | 数据库更新失败 |

---

## Example

### 更新元信息并替换关联合

```bash
curl -X PUT \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/domains/domain_crm" \
  -d '{
    "domainName": "客户关系管理",
    "libraryIds": ["lib_crm", "lib_hr"],
    "termTypeCodes": ["object"]
  }'
```

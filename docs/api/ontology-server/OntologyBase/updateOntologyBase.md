# 更新本体库

```
PUT /api/v1/ontologyBases/{baseId}
```

更新本体库的元信息。所有字段均为可选，仅更新传入的非 `null` 字段（`exclude_none`）。`baseId` 为只读字段，传入也会被忽略。

---

## Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `baseId` | string | 本体库 ID。获取方式见 [listOntologyBases](listOntologyBases.md)。 |

---

## Query Parameters

无

---

## Request Body

```
OntologyBaseUpdate
```

### Schema

```json
{
  "displayName": "CRM 演示库 v2",
  "description": "更新后的描述",
  "ownerType": "enterprise",
  "sourceUrl": "https://new-bio.example.com/DtStudio/daiservice",
  "authType": "api_key",
  "authConfig": {
    "header": "X-API-Key",
    "value": "key_xxx"
  },
  "timeoutSec": 60
}
```

> 以上仅为示意 — 实际请求可只包含需要修改的字段，其余字段不传。

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `displayName` | string | No | 显示名称。 |
| `description` | string | No | 描述。 |
| `sourceUrl` | string | No | 外部服务 base URL。 |
| `authType` | string | No | 鉴权类型：`none` / `api_key` / `bearer` / `oauth2`。 |
| `authConfig` | object | No | 鉴权配置，转发时注入 HTTP header。 |
| `timeoutSec` | integer | No | 转发超时秒数。 |

> **注意：** `baseId` 不可修改，传入也不会生效。

---

## Response Body

```
ApiResponse<OntologyBaseEntry>
```

### Schema

```json
{
  "code": 200,
  "success": true,
  "message": "updated",
  "data": {
    "baseId": "crm_demo",
    "displayName": "CRM 演示库 v2",
    "description": "更新后的描述",
    "ownerType": "enterprise",
    "sourceType": "REMOTE",
    "sourceUrl": "https://new-bio.example.com/DtStudio/daiservice",
    "authType": "api_key",
    "authConfig": {
      "header": "X-API-Key",
      "value": "key_xxx"
    },
    "timeoutSec": 60,
    "createdAt": "",
    "manualBackends": {},
    "backendConfig": {}
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | object | Yes | 更新后的完整本体库信息。 |
| `data.baseId` | string | Yes | 本体库 ID（只读，更新不生效）。 |
| `data.displayName` | string | Yes | 显示名称。 |
| `data.description` | string | Yes | 描述。 |
| `data.ownerType` | string | Yes | `personal` 或 `enterprise`。 |
| `data.sourceType` | string | Yes | `LOCAL` 或 `REMOTE`。 |
| `data.sourceUrl` | string\|null | Yes | REMOTE 时返回外部服务 URL，LOCAL 时为 `null`。 |
| `data.authType` | string\|null | Yes | 鉴权类型。 |
| `data.authConfig` | object\|null | Yes | 鉴权配置。 |
| `data.timeoutSec` | integer | Yes | 转发超时秒数。 |
| `data.createdAt` | string | Yes | 创建时间戳。 |
| `data.manualBackends` | object | Yes | 手动后端映射。 |
| `data.backendConfig` | object | Yes | 后端配置。 |

---

## Errors

| HTTP Status | message Pattern | Condition |
|---|---|---|
| `404` | `OntologyBase '{baseId}' not found` | 指定本体库未注册。 |
| `500` | 服务端异常 | 系统错误。 |

### Error Example

```json
{
  "detail": "OntologyBase 'unknown' not found"
}
```

---

## Example

### 更新显示名称和超时时间

#### Request

```bash
curl -X PUT \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/crm_demo" \
  -d '{
    "displayName": "CRM 演示库 v2",
    "timeoutSec": 60
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "updated",
  "data": {
    "baseId": "crm_demo",
    "displayName": "CRM 演示库 v2",
    "description": "客户关系管理本体库",
    "ownerType": "personal",
    "sourceType": "LOCAL",
    "sourceUrl": null,
    "authType": null,
    "authConfig": null,
    "timeoutSec": 60,
    "createdAt": "",
    "manualBackends": {},
    "backendConfig": {}
  }
}
```

### 切换 ownerType

#### Request

```bash
curl -X PUT \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases/crm_demo" \
  -d '{
    "ownerType": "enterprise"
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "updated",
  "data": {
    "baseId": "crm_demo",
    "displayName": "CRM 演示库 v2",
    "description": "客户关系管理本体库",
    "ownerType": "enterprise",
    "sourceType": "LOCAL",
    "sourceUrl": null,
    "authType": null,
    "authConfig": null,
    "timeoutSec": 60,
    "createdAt": "",
    "manualBackends": {},
    "backendConfig": {}
  }
}
```

---

## 持久化

更新成功后 registry 自动持久化到磁盘。默认路径为 `.datacloud/bases.json`，可通过环境变量 `DATACLOUD_BASE_REGISTRY_PATH` 覆盖。

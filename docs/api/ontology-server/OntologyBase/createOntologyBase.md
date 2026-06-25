# 创建本体库

```
POST /api/v1/ontologyBases
```

创建本体库。`sourceType` 由服务端根据是否提供 `sourceUrl` 自动推导：提供 `sourceUrl` 时为 `REMOTE`，否则为 `LOCAL`。LOCAL 时注册本地 Backend；REMOTE 时转发到外部服务。

---

## Path Parameters

无

---

## Query Parameters

无

---

## Request Body

```
OntologyBaseCreate
```

### Schema

```json
{
  "displayName": "CRM 演示库",
  "description": "客户关系管理本体库",
  "baseId": "crm_demo",
  "ownerType": "personal",
  "sourceUrl": "",
  "authType": "bearer",
  "authConfig": {},
  "timeoutSec": 30
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `displayName` | string | **Yes** | 显示名称。 |
| `description` | string | **Yes** | 描述。 |
| `baseId` | string | No | 可选。不传时雪花算法自动生成 16 位小写 hex ID。传入时须匹配 `^[a-z][a-z0-9_-]{0,15}$`（小写字母开头，1-16 字符，仅允许 a-z 0-9 _ -）。 |
| `ownerType` | string | No | `personal` 或 `enterprise`。默认 `personal`。 |
| `sourceUrl` | string | No | 外部服务 base URL。提供时自动识别为 REMOTE。 |
| `authType` | string | No | 鉴权类型：`none` / `api_key` / `bearer` / `oauth2`。 |
| `authConfig` | object | No | 鉴权配置，转发时注入 HTTP header。 |
| `timeoutSec` | integer | No | 转发超时秒数。默认 `30`。 |

> **雪花 ID 生成规则：** 42-bit 毫秒时间戳 + 22-bit 单调递增序列号，输出为 16 字符小写 hex。线程安全，同一毫秒内序列号自增，序列号耗尽时忙等到下一毫秒。

> **注意：** `sourceType` 由服务端根据 `sourceUrl` 是否为空自动推导，无需显式传入。

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
  "message": "created",
  "data": {
    "baseId": "crm_demo",
    "displayName": "CRM 演示库",
    "description": "客户关系管理本体库",
    "ownerType": "personal",
    "sourceType": "LOCAL",
    "sourceUrl": null,
    "authType": null,
    "authConfig": null,
    "timeoutSec": 30,
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
| `data` | object | Yes | 完整的本体库信息。 |
| `data.baseId` | string | Yes | 本体库 ID（用户传入或雪花算法生成）。 |
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
| `400` | `Invalid baseId '{id}': must match '^[a-z][a-z0-9_-]{0,15}$' …` | `baseId` 格式不合法。 |
| `409` | `OntologyBase '{baseId}' already exists` | `baseId` 重复。 |
| `500` | 服务端异常 | 系统错误。 |

### Error Example

```json
{
  "detail": "Invalid baseId 'UPPER': must match '^[a-z][a-z0-9_-]{0,15}$' (lowercase letter first, 1-16 chars, only a-z, 0-9, _, -)"
}
```

```json
{
  "detail": "OntologyBase 'crm_demo' already exists"
}
```

---

## Example

### 创建 LOCAL 本体库（指定 baseId）

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases" \
  -d '{
    "displayName": "CRM 演示库",
    "description": "客户关系管理本体库",
    "baseId": "crm_demo"
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "created",
  "data": {
    "baseId": "crm_demo",
    "displayName": "CRM 演示库",
    "description": "客户关系管理本体库",
    "ownerType": "personal",
    "sourceType": "LOCAL",
    "sourceUrl": null,
    "authType": null,
    "authConfig": null,
    "timeoutSec": 30,
    "createdAt": "",
    "manualBackends": {},
    "backendConfig": {}
  }
}
```

### 创建 LOCAL 本体库（自动生成 baseId）

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases" \
  -d '{
    "displayName": "临时测试库",
    "description": "自动生成 ID 的测试库"
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "created",
  "data": {
    "baseId": "019b2e8f00001a3c",
    "displayName": "临时测试库",
    "description": "自动生成 ID 的测试库",
    "ownerType": "personal",
    "sourceType": "LOCAL",
    "sourceUrl": null,
    "authType": null,
    "authConfig": null,
    "timeoutSec": 30,
    "createdAt": "",
    "manualBackends": {},
    "backendConfig": {}
  }
}
```

### 创建 REMOTE 本体库

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases" \
  -d '{
    "displayName": "生物信息平台",
    "description": "外部生物信息本体库",
    "baseId": "bio_platform",
    "sourceUrl": "https://bio.example.com/DtStudio/daiservice",
    "authType": "bearer",
    "authConfig": {
      "header": "Authorization",
      "value": "Bearer tok_xxx"
    },
    "timeoutSec": 30
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "created",
  "data": {
    "baseId": "bio_platform",
    "displayName": "生物信息平台",
    "description": "外部生物信息本体库",
    "ownerType": "personal",
    "sourceType": "REMOTE",
    "sourceUrl": "https://bio.example.com/DtStudio/daiservice",
    "authType": "bearer",
    "authConfig": {
      "header": "Authorization",
      "value": "Bearer tok_xxx"
    },
    "timeoutSec": 30,
    "createdAt": "",
    "manualBackends": {},
    "backendConfig": {}
  }
}
```

---

## 持久化

创建成功后 registry 自动持久化到磁盘。默认路径为 `.datacloud/bases.json`，可通过环境变量 `DATACLOUD_BASE_REGISTRY_PATH` 覆盖。

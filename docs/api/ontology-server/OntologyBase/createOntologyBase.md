# 创建本体库（返回值分配一个唯一表示ID, 不分本地远程，统一一个url\port\鉴权信息）

```
POST /api/v1/ontologyBases
```

创建本体库。`sourceType=LOCAL` 时自动初始化 `default` 场景及目录结构；`sourceType=REMOTE` 时注册外部服务连接信息并执行健康检查。

---

## Path Parameters

无

---

## Query Parameters

无

---

## Request Body

```
CreateNamespaceRequest
```

### Schema

```json
{
  "baseId": "crm_demo",
  "displayName": "CRM 演示库",
  "description": "",
  "ownerType": "personal",
  "sourceType": "LOCAL",
  "sourceUrl": "",
  "authType": "bearer",
  "authConfig": {},
  "timeoutSec": 30
}
```

> **注意：** `sourceType` 由服务端根据是否提供 `sourceUrl` 自动推导，无需显式传入。提供 `sourceUrl` 时自动识别为 `REMOTE`，否则为 `LOCAL`。

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `ownerType` | string | Yes | personal / enterprise |
| `baseId` | string | Yes | 不可变的 ID，创建后不可改。 |
| `displayName` | string | Yes | 显示名称。 |
| `description` | string | No | 描述。 |
| `sourceType` | string | No | `LOCAL` 或 `REMOTE`。服务端根据是否提供 `sourceUrl` 自动推导，无需显式传入。 |

### REMOTE 额外字段

| Field | Type | Required | Description |
|---|---|---|---|
| `sourceUrl` | string | Yes | 外部服务 base URL。 |
| `authType` | string | No | `none` / `api_key` / `bearer` / `oauth2`。默认 `none`。 |
| `authConfig` | object | No | 鉴权配置，转发时注入 HTTP header。 |
| `timeoutSec` | integer | No | 转发超时秒数。默认 `30`。 |

---

## Response Body

```
CreateNamespaceResponse
```

### Schema

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "baseId": "crm_demo"
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | object | Yes | 创建的本体库摘要。失败时为 `null`。 |
| `data.baseId` | string | Yes | 本体库 ID | |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：baseId 不能为空` | `baseId` 未传或为空。 |
| `409` | 409 | `本体库「{baseId}」已存在` | `baseId` 重复。 |
| `500` | 500 | `系统错误：{原因}` | 服务端异常。 |

### Error Example

```json
{
  "code": 409,
  "success": false,
  "message": "本体库「crm_demo」已存在",
  "data": null
}
```

---

## Example

### 创建 LOCAL 本体库

#### Request

```bash
curl -X POST \
  -H "Content-type: application/json" \
  "https://$HOSTNAME/api/v1/ontologyBases" \
  -d '{
    "baseId": "crm_demo",
    "displayName": "CRM 演示库",
    "description": ""
  }'
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "baseId": "crm_demo"
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
    "baseId": "bio_platform",
    "displayName": "生物信息平台",
    "description": "",
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
  "message": "创建成功",
  "data": {
    "baseId": "bio_platform"
  }
}
```

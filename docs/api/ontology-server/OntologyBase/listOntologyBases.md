# 列出本体库

```
GET /api/v1/ontologyBases
GET /api/v1/ontologyBases/{ownerType}
```

列出已注册的本体库。可按 `ownerType` 过滤，亦可按关键词 `keyword` 模糊查询本体库名称、描述或 ID。

---

## Path Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `ownerType` | string | No（仅第二个 URL 变体） | `personal` 或 `enterprise`。不传时列出所有 owner_type 的本体库。 |

---

## Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `keyword` | string | No | 查询关键词。大小写不敏感，模糊匹配 `displayName`、`description`、`baseId`。

---

## Request Body

无

---

## Response Body

```
ListNamespacesResponse
```

### Schema

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "baseId": "crm_demo",
      "displayName": "CRM 演示库",
      "description": "",
      "sourceType": "LOCAL"
    },
    {
      "baseId": "bio_platform",
      "displayName": "生物信息平台",
      "description": "",
      "sourceType": "REMOTE",
      "sourceUrl": "https://bio.example.com/DtStudio/daiservice",
      "healthStatus": "ok"
    }
  ]
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | Yes | 业务状态码。`200` 为成功。 |
| `success` | boolean | Yes | 是否成功。 |
| `message` | string | Yes | 结果描述。 |
| `data` | array | Yes | 本体库列表。失败时为 `null`。 |
| `data[].baseId` | string | Yes | 不可变的 ID。 |
| `data[].displayName` | string | Yes | 显示名称。 |
| `data[].description` | string | No | 描述。 |
| `data[].sourceType` | string | Yes | `LOCAL` 或 `REMOTE`。 |
| `data[].sourceUrl` | string | No | REMOTE 时，外部服务的 base URL。 |
| `data[].healthStatus` | string | No | REMOTE 时，`ok` / `degraded` / `unreachable`。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `500` | 500 | `系统错误：{原因}` | 服务端异常 |

### Error Example

```json
{
  "code": 500,
  "success": false,
  "message": "系统错误：registry 加载失败",
  "data": null
}
```

---

## Example

### 列出所有本体库

#### Request

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases"
```

#### Response

```json
{
  "code": 200,
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "baseId": "crm_demo",
      "displayName": "CRM 演示库",
      "description": "",
      "sourceType": "LOCAL"
    },
    {
      "baseId": "bio_platform",
      "displayName": "生物信息平台",
      "description": "",
      "sourceType": "REMOTE",
      "sourceUrl": "https://bio.example.com/DtStudio/daiservice",
      "healthStatus": "ok"
    }
  ]
}
```

### 按 ownerType 过滤

#### Request

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases/personal"
```

### 按关键词模糊查询

#### Request

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases?keyword=CRM"
```

### 按 ownerType + 关键词过滤

#### Request

```bash
curl -X GET \
  "https://$HOSTNAME/api/v1/ontologyBases/enterprise?keyword=platform"
```

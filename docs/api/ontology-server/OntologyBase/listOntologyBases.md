# 列出本体库

```
GET /api/v1/ontologyBases
```

列出所有已注册的本体库，含 LOCAL 和 REMOTE。

---

## Path Parameters

无

---

## Query Parameters

无

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

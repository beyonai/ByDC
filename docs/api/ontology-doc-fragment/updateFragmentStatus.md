# 批量更新文档片段状态

```
POST /api/v1/rpc/ontologyDocFragment/updateStatus
```

根据主键 ID 列表批量更新本体文档片段的融合状态。

---

## Request Headers

| Header | Required | Description |
|---|---|---|
| `X-User-Code` | Yes | 操作人标识，写入 `updated_by` 字段。 |
| `Content-Type` | Yes | `application/json` |

---

## Request Body

```json
{
  "params": {
    "ids": [101, 102, 103],
    "status": 1
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `params.ids` | integer[] | Yes | 待更新记录的主键 ID 列表，不可为空。 |
| `params.status` | integer | Yes | 目标融合状态。`0`=未融合，`1`=已融合。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "ok",
  "data": {
    "updated": 3
  }
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `data.updated` | integer | 实际更新的行数。若 `ids` 中有不存在的主键，只计入实际命中行数。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `ids is required and must be a non-empty list` | `ids` 为空或未传。 |
| `400` | 400 | `status is required` | `status` 未传。 |
| `400` | 400 | `status must be 0 (未融合) or 1 (已融合)` | `status` 传入非 `0`/`1` 的值。 |
| `400` | 400 | `Request header 'X-User-Code' is required` | 缺少 `X-User-Code` 请求头。 |
| `500` | 500 | `Internal error` | 数据库写入失败。 |

---

## Example

### 将片段标记为已融合

```bash
curl -X POST "https://$HOSTNAME/api/v1/rpc/ontologyDocFragment/updateStatus" \
  -H "Content-Type: application/json" \
  -H "X-User-Code: user001" \
  -d '{
    "params": {
      "ids": [101, 102, 103],
      "status": 1
    }
  }'
```

### 响应示例

```json
{
  "code": 200,
  "success": true,
  "message": "ok",
  "data": {
    "updated": 3
  }
}
```

### 将片段重置为未融合

```bash
curl -X POST "https://$HOSTNAME/api/v1/rpc/ontologyDocFragment/updateStatus" \
  -H "Content-Type: application/json" \
  -H "X-User-Code: user001" \
  -d '{
    "params": {
      "ids": [101],
      "status": 0
    }
  }'
```

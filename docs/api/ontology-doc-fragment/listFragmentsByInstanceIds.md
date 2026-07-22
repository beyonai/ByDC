# 按实例 ID 列表查询文档片段

```
POST /api/v1/rpc/ontologyDocFragment/listByInstanceIds
```

根据实例 ID 列表分页查询本体文档片段记录。支持按融合状态过滤。

---

## Request Headers

| Header | Required | Description |
|---|---|---|
| `Content-Type` | Yes | `application/json` |

---

## Request Body

```json
{
  "params": {
    "instanceIds": ["term-uuid-001", "term-uuid-003"],
    "status": 0,
    "page_index": 1,
    "page_size": 20
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `params.instanceIds` | string[] | Yes | 实例 ID 列表，对应 `instance_id` 字段。 |
| `params.status` | integer | No | 融合状态过滤。`0`=未融合，`1`=已融合。不传或为 `null` 则返回全部状态。 |
| `params.page_index` | integer | No | 页码，从 `1` 开始，默认 `1`。 |
| `params.page_size` | integer | No | 每页记录数，默认 `20`。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "ok",
  "data": {
    "total": 2,
    "data": [
      {
        "id": 101,
        "instance_id": "term-uuid-001",
        "instance_name": "订单金额",
        "content": "这是第一段片段内容",
        "status": 0,
        "origin_instance_id": "term-uuid-002",
        "origin_file": {
          "kb_resource_id": "res-001",
          "kb_id": "kb-001",
          "file_path": "/docs/order.pdf"
        },
        "created_time": "2026-07-21T10:00:00+00:00",
        "created_by": "user001",
        "updated_time": null,
        "updated_by": null
      }
    ]
  }
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `data.total` | integer | 符合条件的总记录数。 |
| `data.data` | object[] | 当前页片段记录列表。 |
| `data.data[].id` | integer | 主键 ID。 |
| `data.data[].instance_id` | string | 实例 term_id。 |
| `data.data[].instance_name` | string | 实例名称（来自 term 表的 term_name）。 |
| `data.data[].content` | string | 片段文本内容。 |
| `data.data[].status` | integer | 融合状态。`0`=未融合，`1`=已融合。 |
| `data.data[].origin_instance_id` | string \| null | 原文件实例 term_id。 |
| `data.data[].origin_file` | object | 原文件信息，包含 `kb_resource_id`、`kb_id`、`file_path`。 |
| `data.data[].created_time` | string | 创建时间，ISO 8601 格式。 |
| `data.data[].created_by` | string | 创建人。 |
| `data.data[].updated_time` | string \| null | 更新时间，ISO 8601 格式。未更新时为 `null`。 |
| `data.data[].updated_by` | string \| null | 更新人。未更新时为 `null`。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `instance_ids / instanceIds is required` | `instanceIds` 为空或未传。 |
| `400` | 400 | `status must be 0 (未融合) or 1 (已融合)` | `status` 传入非 `0`/`1` 的值。 |
| `500` | 500 | `Internal error` | 数据库查询失败。 |

---

## Example

### 查询全部状态

```bash
curl -X POST "https://$HOSTNAME/api/v1/rpc/ontologyDocFragment/listByInstanceIds" \
  -H "Content-Type: application/json" \
  -d '{
    "params": {
      "instanceIds": ["term-uuid-001", "term-uuid-003"],
      "page_index": 1,
      "page_size": 20
    }
  }'
```

### 只查未融合（status=0）

```bash
curl -X POST "https://$HOSTNAME/api/v1/rpc/ontologyDocFragment/listByInstanceIds" \
  -H "Content-Type: application/json" \
  -d '{
    "params": {
      "instanceIds": ["term-uuid-001", "term-uuid-003"],
      "status": 0
    }
  }'
```

### 只查已融合（status=1）

```bash
curl -X POST "https://$HOSTNAME/api/v1/rpc/ontologyDocFragment/listByInstanceIds" \
  -H "Content-Type: application/json" \
  -d '{
    "params": {
      "instanceIds": ["term-uuid-001"],
      "status": 1
    }
  }'
```

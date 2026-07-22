# 批量创建本体文档片段

```
POST /api/v1/rpc/ontologyDocFragment/batchCreate
```

批量创建本体文档片段记录。系统自动通过 `instanceId` 和 `originInstanceId` 从 term 表查询实例名称及原文件信息，写入 `instance_name` 和 `origin_file` 字段。若任意 `instanceId` 在 term 表中不存在，整批请求拒绝写入。

---

## Request Headers

| Header | Required | Description |
|---|---|---|
| `X-User-Code` | Yes | 操作人标识，写入 `created_by` 字段。 |
| `Content-Type` | Yes | `application/json` |

---

## Request Body

```json
{
  "params": {
    "items": [
      {
        "instanceId": "term-uuid-001",
        "originInstanceId": "term-uuid-002",
        "content": "这是第一段片段内容"
      },
      {
        "instanceId": "term-uuid-003",
        "content": "这是第二段片段内容，无原文件实例"
      }
    ]
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `params.items` | object[] | Yes | 待创建的片段列表，不可为空。 |
| `params.items[].instanceId` | string | Yes | 实例 term_id。必须在 term 表中存在，系统自动查询对应 `term_name` 作为 `instance_name`。 |
| `params.items[].originInstanceId` | string | No | 原文件实例 term_id。系统从该 term 的 `ext_attrs` 中提取 `kb_resource_id`、`kb_id`、`file_path` 写入 `origin_file`。 |
| `params.items[].content` | string | Yes | 片段文本内容。 |

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "created",
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
    },
    {
      "id": 102,
      "instance_id": "term-uuid-003",
      "instance_name": "客户名称",
      "content": "这是第二段片段内容，无原文件实例",
      "status": 0,
      "origin_instance_id": null,
      "origin_file": {},
      "created_time": "2026-07-21T10:00:00+00:00",
      "created_by": "user001",
      "updated_time": null,
      "updated_by": null
    }
  ]
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `data` | object[] | 新创建的片段记录列表，顺序与请求 `items` 一一对应。 |
| `data[].id` | integer | 主键 ID。 |
| `data[].instance_id` | string | 实例 term_id。 |
| `data[].instance_name` | string | 实例名称（来自 term 表的 term_name）。 |
| `data[].content` | string | 片段文本内容。 |
| `data[].status` | integer | 融合状态，新建默认为 `0`（未融合）。 |
| `data[].origin_instance_id` | string \| null | 原文件实例 term_id。 |
| `data[].origin_file` | object | 原文件信息，包含 `kb_resource_id`、`kb_id`、`file_path`。无原文件时为 `{}`。 |
| `data[].created_time` | string | 创建时间，ISO 8601 格式。 |
| `data[].created_by` | string | 创建人。 |
| `data[].updated_time` | string \| null | 更新时间，新建时为 `null`。 |
| `data[].updated_by` | string \| null | 更新人，新建时为 `null`。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `items is required and must be a non-empty list` | `items` 为空或未传。 |
| `400` | 400 | `Request header 'X-User-Code' is required` | 缺少 `X-User-Code` 请求头。 |
| `400` | 400 | `以下 instance_id 在 term 表中不存在: {id1}, {id2}` | 有 `instanceId` 在 term 表中查不到，整批拒绝写入。 |
| `500` | 500 | `Internal error` | 数据库写入失败。 |

---

## Example

```bash
curl -X POST "https://$HOSTNAME/api/v1/rpc/ontologyDocFragment/batchCreate" \
  -H "Content-Type: application/json" \
  -H "X-User-Code: user001" \
  -d '{
    "params": {
      "items": [
        {
          "instanceId": "term-uuid-001",
          "originInstanceId": "term-uuid-002",
          "content": "这是第一段片段内容"
        },
        {
          "instanceId": "term-uuid-003",
          "content": "这是第二段片段内容，无原文件实例"
        }
      ]
    }
  }'
```

### 响应示例

```json
{
  "code": 200,
  "success": true,
  "message": "created",
  "data": [
    {
      "id": 101,
      "instance_id": "term-uuid-001",
      "instance_name": "订单金额",
      "content": "这是第一段片段内容",
      "status": 0,
      "origin_instance_id": "term-uuid-002",
      "origin_file": {"kb_resource_id": "res-001", "kb_id": "kb-001", "file_path": "/docs/order.pdf"},
      "created_time": "2026-07-21T10:00:00+00:00",
      "created_by": "user001",
      "updated_time": null,
      "updated_by": null
    },
    {
      "id": 102,
      "instance_id": "term-uuid-003",
      "instance_name": "客户名称",
      "content": "这是第二段片段内容，无原文件实例",
      "status": 0,
      "origin_instance_id": null,
      "origin_file": {},
      "created_time": "2026-07-21T10:00:00+00:00",
      "created_by": "user001",
      "updated_time": null,
      "updated_by": null
    }
  ]
}
```

### instanceId 不存在时的错误响应

```json
{
  "code": 400,
  "success": true,
  "message": "以下 instance_id 在 term 表中不存在: term-uuid-bad",
  "data": null
}
```

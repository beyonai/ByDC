# 调用知识库动作

```
POST /api/v1/rpc/kb/invokeAction
```

通过本体加载器 + 执行后端流水线调用 KB 动作。底层等价于 SDK 调用：

```python
loader.get_object(object_code).invoke_action(action_code, arguments)
```

支持所有由 `inject_virtual_actions` 注入的 KB 动作类型：
- `write_*`：写入文档到知识库
- `search_*`：语义检索
- `search_by_file_name_*`：按文件名约束的分片检索
- `merge_write_*` / `update_kb_*`：融合更新
- `delete_kb_*`：删除知识库文档

---

## Request Headers

| Header | Required | Description |
|---|---|---|
| `Content-Type` | Yes | `application/json` |
| `Beyond-Token` | Yes | ByClaw UserFS 认证 token，同时注入到 `InvocationContext.token`，用于知识库文件读写及执行后端鉴权。 |
| `X-Tenant-Id` | No | 租户 ID，注入到 `InvocationContext.tenant_id`。 |
| `X-User-Code` | No | 用户编码，注入到 `InvocationContext.user_id`。 |
| `X-Session-Id` | No | 会话 ID，注入到 `InvocationContext.session_id`。 |
| `X-Language` | No | 语言编码（如 `zh_CN`、`en_US`），控制执行后端的返回语言。 |

---

## Request Body

```json
{
  "params": {
    "objectCode": "sales_meeting_note_0027024630",
    "actionCode": "write_sales_meeting_note_0027024630",
    "arguments": {
      "source_path": "/会议纪要/端到端故障排查会议纪要.md",
      "content": "# 会议纪要\n\n会议时间：2026-04-22...",
      "file_description": "端到端流程故障排查会议纪要",
      "labels": {
        "meetingTitle": "端到端流程故障排查会议纪要",
        "meetingTime": "2026-04-22 20:52:25",
        "participantEmpNos": ["王威", "陈晓锋"]
      }
    }
  }
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `params.objectCode` | string | Yes | 本体对象编码。也可用 `object_code`（snake_case）。 |
| `params.actionCode` | string | Yes | 动作编码，如 `write_xxx`、`search_xxx`。也可用 `action_code`。 |
| `params.arguments` | object | No | 传给动作的参数，原样透传给执行后端。 |
| `params.base_id` | string | No | 基础库 ID，默认使用全局 `DEFAULT_BASE_ID`。 |

### arguments 常用字段（write_* 动作）

| Field | Type | Required | Description |
|---|---|---|---|
| `source_path` | string | Yes | 文档在知识库中的路径，必须以 `/` 开头。 |
| `content` | string | Yes | Markdown 文档正文。 |
| `labels` | object | No | 元数据标签，渲染为 YAML Front Matter 嵌入文档头部。 |
| `file_description` | string | No | 文件描述。 |

### arguments 常用字段（search_* 动作）

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | Yes | 语义检索文本。 |
| `select` | string[] | No | 返回的字段列表。 |
| `filters` | object[] | No | 过滤条件，格式：`[{"field": "...", "op": "eq", "value": "..."}]`。 |
| `limit` | integer | No | 最大返回记录数。 |

---

## Response Body

```json
{
    "code": 200,
    "success": true,
    "message": "ok",
    "data": {
        "records": [
            {
                "name": "智能客服机器人",
                "ability_definition": "通过自然语言处理技术，自动响应用户咨询，支持多轮对话与意图识别，7×24 小时不间断服务。",
                "audience": "最终用户",
                "product_code": "PROD_CS_001",
                "fileName": "智能客服机器人能力.md",
                "filePath": "/Ability/智能客服机器人能力.md",
                "_write_note": "已成功写入知识库，文件路径：/Ability/智能客服机器人能力.md；同时把已打标的文件写入到会话空间，路径：/datacloud/kb/智能客服机器人能力.md",
                "term_id": "c692a63b-4de6-40d5-b566-0409708f8b7a"
            }
        ],
        "total": 1,
        "meta": {
            "columns": [
                {
                    "name": "name",
                    "label": "名称",
                    "type": "string"
                },
                {
                    "name": "ability_definition",
                    "label": "能力描述",
                    "type": "string"
                },
                {
                    "name": "audience",
                    "label": "服务对象",
                    "type": "string"
                },
                {
                    "name": "product_code",
                    "label": "归属产品",
                    "type": "string"
                },
                {
                    "name": "fileName",
                    "label": "文件名称",
                    "type": "string"
                },
                {
                    "name": "filePath",
                    "label": "文件路径",
                    "type": "string"
                },
                {
                    "name": "_write_note",
                    "label": "写入说明",
                    "type": "string"
                },
                {
                    "name": "term_id",
                    "label": "术语ID",
                    "type": "string"
                }
            ],
            "object_code": "Ability",
            "datasource_alias": "Ability",
            "query": "",
            "kb_files": [
                "/Ability/智能客服机器人能力.md"
            ],
            "synced_term_ids": [
                "c692a63b-4de6-40d5-b566-0409708f8b7a"
            ],
            "_write_note": "已成功写入知识库，文件路径：/Ability/智能客服机器人能力.md；同时把已打标的文件写入到会话空间，路径：/datacloud/kb/智能客服机器人能力.md",
            "session_files": [
                "/datacloud/kb/智能客服机器人能力.md"
            ],
            "viewId": "auto_view",
            "total": 1
        }
    }
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `data.records` | object[] | 动作执行结果记录列表。write_* 动作包含写入的字段及 `_write_note`；search_* 动作包含匹配的文档片段。 |
| `data.total` | integer | 记录总数。 |
| `data.meta` | object | 执行元数据，包含 `object_code`、`datasource_alias`、`kb_files`、`synced_term_ids`、`session_files`、`columns` 等。 |

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `object_code / objectCode is required` | 未传 `objectCode`。 |
| `400` | 400 | `action_code / actionCode is required` | 未传 `actionCode`。 |
| `403` | 403 | `Execution not available for base ...` | 该 base_id 未配置执行后端。 |
| `500` | 500 | `Internal error` | 知识库服务调用失败。 |

---

## 示例：写入文档（Ability 对象）

`Ability` 对象 `object_code` 为 `Ability`，写入动作码为 `write_Ability`。

```bash
curl -X POST "https://$HOSTNAME/api/v1/rpc/kb/invokeAction" \
  -H "Content-Type: application/json" \
  -H "Beyond-Token: $BEYOND_TOKEN" \
  -d '{
    "params": {
      "objectCode": "Ability",
      "actionCode": "write_Ability",
      "arguments": {
        "source_path": "/Ability/智能客服机器人能力.md",
        "content": "# 智能客服机器人能力\n\n## 能力描述\n\n通过自然语言处理技术，自动响应用户咨询，支持多轮对话与意图识别，7×24 小时不间断服务。\n\n## 适用场景\n\n适用于电商、金融、企业服务等场景，有效降低人工客服成本。",
        "file_description": "智能客服机器人产品能力说明",
        "labels": {
          "name": "智能客服机器人",
          "ability_definition": "通过自然语言处理技术，自动响应用户咨询，支持多轮对话与意图识别，7×24 小时不间断服务。",
          "audience": "最终用户",
          "product_code": "PROD_CS_001"
        }
      }
    }
  }'
```

## 示例：语义检索（Ability 对象）

```bash
curl -X POST "https://$HOSTNAME/api/v1/rpc/kb/invokeAction" \
  -H "Content-Type: application/json" \
  -H "Beyond-Token: $BEYOND_TOKEN" \
  -d '{
    "params": {
      "objectCode": "Ability",
      "actionCode": "search_Ability",
      "arguments": {
        "query": "智能客服自动回复",
        "select": ["name", "ability_definition", "audience", "product_code"],
        "filters": [
          {"field": "audience", "op": "eq", "value": "最终用户"}
        ],
        "limit": 5
      }
    }
  }'
```

## 示例：按文件名检索（Ability 对象）

```bash
curl -X POST "https://$HOSTNAME/api/v1/rpc/kb/invokeAction" \
  -H "Content-Type: application/json" \
  -H "Beyond-Token: $BEYOND_TOKEN" \
  -d '{
    "params": {
      "objectCode": "Ability",
      "actionCode": "search_by_file_name_Ability",
      "arguments": {
        "query": "客服",
        "select": ["name", "ability_definition"],
        "limit": 10
      }
    }
  }'
```

## 示例：删除文档（Ability 对象）

```bash
curl -X POST "https://$HOSTNAME/api/v1/rpc/kb/invokeAction" \
  -H "Content-Type: application/json" \
  -H "Beyond-Token: $BEYOND_TOKEN" \
  -d '{
    "params": {
      "objectCode": "Ability",
      "actionCode": "delete_kb_Ability",
      "arguments": {
        "source_path": "/Ability/智能客服机器人能力.md"
      }
    }
  }'
```

---

## 动作码命名规则

动作码由 `{action_type}_{object_code}` 构成：

| 动作类型 | 动作码格式 | 说明 |
|---|---|---|
| 写入 | `write_{object_code}` | 写入或覆盖一篇文档 |
| 语义检索 | `search_{object_code}` | 向量语义检索 |
| 文件名检索 | `search_by_file_name_{object_code}` | 按文件名约束的分片检索 |
| 融合更新 | `merge_write_{object_code}` | 智能合并更新已有文档 |
| 删除 | `delete_kb_{object_code}` | 删除知识库中的文档 |

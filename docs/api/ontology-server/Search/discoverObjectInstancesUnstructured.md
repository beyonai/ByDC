# 非结构化对象实例发现

```
POST /api/v1/rpc/search/discoverObjectInstancesUnstructured
```

从输入实例（`instance_id`，term_id）对应的知识库文件中发现对象实例：既包括库中
已有实例，也包括文件中出现但尚未入库的候选实例。新发现的实例自动创建（write
action 写入知识库文件）、登记文件状态，并与输入实例建立「提及」关系（单向
源→目标，幂等）。

> **本版状态**：已有实例发现 / 新实例 LLM 抽取为 TODO 占位，调用即返回
> `501 not_implemented`。新实例创建 / 文件登记 / 提及关系为已实现能力
> （以单元测试验收，待发现逻辑接入后由编排串联）。

---

## RPC Payload

所有参数放在 `params` 内。

```json
{
  "params": {
    "base_id": "BYCLAW_DATACLOUD",
    "instance_id": "b691924f-9efb-45ec-999c-a2fc4ec01d18",
    "object_codes": ["Methodology", "Concept"]
  }
}
```

请求头要求 `X-Session-Id`（用于文件登记条目的 `sessionId` 字段）。

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `base_id` | string | No | `BYCLAW_DATACLOUD` | 本体库 ID。 |
| `instance_id` | string | Yes | — | 输入实例 ID（term_id）。空值返回 400。 |
| `object_codes` | string[] | Yes | — | 非结构化对象类型编码列表，双语义：已有实例匹配范围 + 新实例候选类型。空/缺失返回 400。 |

### Headers

| Header | Required | Description |
|---|---|---|
| `X-Session-Id` | Yes | 会话 ID，透传为文件登记条目的 `sessionId`。缺失返回 400。 |

---

## 流程

```
输入实例（instance_id）
  │
  ├─ ① 参数校验（instance_id 非空、object_codes 非空）
  ├─ ② 定位知识库文件并读取全文（get_document_content_by_term_id）
  ├─ ③ 已有实例发现（TODO 占位 → 501）
  ├─ ④ 新实例发现 / LLM 抽取（TODO 占位 → 501）
  ├─ ⑤ 新实例创建（write_<object_code> action，services/object_action.py）
  ├─ ⑥ term_id 强校验（write 响应缺 term_id → 500，不延迟不 pending）
  ├─ ⑦ 文件登记（save_or_update_object_files，statusCd=待整理）
  ├─ ⑧ 「提及」关系（源=输入实例 → 目标=发现实例，单向幂等）
  └─ ⑨ 返回 {items: [已有..., 新...]}，每项含 is_new 标记
```

全程同步、无降级：任何异常直接上抛，由 RPC 层统一映射为错误码。

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "ok",
  "data": {
    "items": [
      {
        "instance_id": "1954df64-e0c7-4f56-9816-b2e87ad4e0d0",
        "instance_code": "Agent",
        "instance_name": "Agent",
        "object_code": "Concept",
        "file_name": "/Concept/Agent.md",
        "kb_resource_id": "kb-res-1",
        "kb_id": "kb-1",
        "is_new": false,
        "evidence": null,
        "relation_name": "提及"
      },
      {
        "instance_id": "b691924f-9efb-45ec-999c-a2fc4ec01d18",
        "instance_code": "工具编排器",
        "instance_name": "工具编排器",
        "object_code": "Methodology",
        "file_name": "/Methodology/工具编排器.md",
        "kb_resource_id": null,
        "kb_id": null,
        "is_new": true,
        "evidence": null,
        "relation_name": "提及"
      }
    ]
  }
}
```

### Hit 字段

| Field | Type | Description |
|---|---|---|
| `instance_id` | string | 实例 ID（term_id）。已有实例为库中原值；新实例为 write action 强校验非空的已创建 term_id。 |
| `instance_code` | string | 实例编码（term_code）。 |
| `instance_name` | string | 实例名称（term_name）。 |
| `object_code` | string | 所属对象类型编码（term_type / object_code）。 |
| `file_name` | string \| null | 对应知识库文件路径。 |
| `kb_resource_id` | string \| null | 知识库资源 ID。 |
| `kb_id` | string \| null | 知识库 ID。 |
| `is_new` | boolean | `true`=本次新创建，`false`=库中已有。 |
| `evidence` | string \| null | 原文证据片段；本版恒为 `null`（TODO）。 |
| `relation_name` | string | 已建立/将建立的关系名，恒为「提及」。 |

---

## Error Codes

| HTTP | err_code | 触发点 |
|---|---|---|
| 400 | `invalid_params` | 入参非法（`instance_id` 空 / `object_codes` 空或缺失）；`X-Session-Id` 缺失；term 缺 `kb_resource_id`/`kb_file_path` 定位信息 |
| 403 | `permission_denied` | execution / term backend 无权限 |
| 404 | `not_found` | 输入 term 不存在 |
| 500 | `internal_error` | 读文件失败；write 响应缺 `term_id`（强校验）；其他任何异常 |
| 501 | `not_implemented` | ③ 已有实例发现 / ④ 新实例发现 TODO 占位（本版） |

---

## Example

```bash
curl -s http://localhost:8088/api/v1/rpc/search/discoverObjectInstancesUnstructured \
  -X POST -H "Content-Type: application/json" -H "X-Session-Id: session-1" \
  -d '{
    "params": {
      "base_id": "BYCLAW_DATACLOUD",
      "instance_id": "b691924f-9efb-45ec-999c-a2fc4ec01d18",
      "object_codes": ["Methodology", "Concept"]
    }
  }'
```

本版预期响应（③ 占位短路）：

```json
{
  "code": 501,
  "success": true,
  "message": "existing instance discovery is not implemented",
  "data": null
}
```

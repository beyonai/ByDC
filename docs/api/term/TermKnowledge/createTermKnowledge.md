# 创建术语知识

```
POST /api/v1/knowledge/termKnowledges
```

为术语挂载关联知识。支持内部落地（descSummary/desc）和外挂知识库（extSystem/extKbId/extDocId）两种模式。至少一种内容不为空。需要 knowledge 服务鉴权。

---

## Path Parameters

无。

---

## Request Body

```json
{
  "knowledgeId": "kb_001",         // string，可选。知识 ID，不传则自动生成
  "termId": "term_customer",       // string，必填。归属术语 ID
  "descSummary": "客户主数据管理规范", // string，可选。知识摘要（约 200 字）
  "desc": "完整的客户主数据模型定义...",// string，可选。知识原文
  "extSystem": null,               // string，可选。外部系统编码
  "extKbId": null,                 // string，可选。外部知识库 ID
  "extDocId": null,                // string，可选。外部文档 ID
  "sortOrder": 0                   // integer，可选。展示排序，默认 0
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `knowledgeId` | string | No | 知识 ID。不传时服务端雪花算法自动生成。 |
| `termId` | string | Yes | 归属术语 ID。 |
| `descSummary` | string | No | 知识摘要（约 200 字）。内部落地模式填写。 |
| `desc` | string | No | 知识原文。内部落地模式填写。 |
| `extSystem` | string | No | 外部系统编码。外挂模式填写（如 `"RAGFLOW"`、`"DIFY"`、`"CONFLUENCE"`）。 |
| `extKbId` | string | No | 外部知识库 ID。外挂模式必填。 |
| `extDocId` | string | No | 外部文档 ID。外挂模式必填。外挂时由外部 KB 负责 chunk embedding 与向量检索。 |
| `sortOrder` | integer | No | 同一术语下多条知识的展示排序。默认 0。 |

### 字段说明

> **内部落地模式**：`descSummary` / `desc` 至少一个有值，`extSystem` 为空。知识内容存储在库内，支持本地全文检索。
>
> **外挂知识库模式**：`extSystem` + `extKbId` + `extDocId` 均有值，`descSummary` / `desc` 可为空。知识内容由外部系统管理。
>
> **完整性约束**：`descSummary IS NOT NULL OR desc IS NOT NULL OR extDocId IS NOT NULL`，三种至少一种不为空。

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "创建成功",
  "data": {
    "knowledgeId": "kb_001",
    "termId": "term_customer",
    "descSummary": "客户主数据管理规范",
    "desc": "完整的客户主数据模型定义，包含基本信息...",
    "extSystem": null,
    "extKbId": null,
    "extDocId": null,
    "sortOrder": 0,
    "createdTime": "2026-07-02 10:00:00",
    "updatedTime": "2026-07-02 10:00:00"
  }
}
```

---

## Errors

| code | HTTP Status | message Pattern | Condition |
|---|---|---|---|
| `400` | 400 | `参数错误：{具体原因}` | `termId` 缺失；内容全部为空（descSummary/desc/extDocId 均为 null）；`termId` 不存在 |
| `400` | 400 | `参数错误：外挂模式需同时提供 extSystem 和 extKbId` | `extDocId` 有值但 `extSystem` 或 `extKbId` 为空 |
| `500` | 500 | `系统错误：{原因}` | 数据库写入失败 |

---

## Example

### 内部落地知识

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termKnowledges" \
  -d '{
    "termId": "term_customer",
    "descSummary": "客户主数据管理规范",
    "desc": "客户是企业的核心业务对象，包含基本信息、联系信息、财务信息...",
    "sortOrder": 0
  }'
```

### 外挂知识库引用

```bash
curl -X POST \
  -H "Content-type: application/json" \
  -H "Authorization: Bearer *** \
  "https://$HOSTNAME/api/v1/knowledge/termKnowledges" \
  -d '{
    "termId": "term_order",
    "extSystem": "RAGFLOW",
    "extKbId": "kb_crm_docs",
    "extDocId": "doc_order_guide_2026",
    "sortOrder": 1
  }'
```

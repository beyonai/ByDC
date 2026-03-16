# M4 知识库 + M5 Skills API 设计文档

> **日期**：2026-03-08
> **状态**：已确认
> **范围**：M4 知识库（#68-71）、M5 Skills API（#72-74）

---

## 1 M4 知识库

### 1.1 目标与范围

- **目标**：支持 `source_type=KNOWLEDGE_BASE` 对象，通过 HTTP 调用外部 RAG 服务做向量检索，并按对象字段作为 tag 过滤。
- **范围**：#68-71（本体已有 KNOWLEDGE_BASE，重点在连接器、PlanStep、结果转换）。

### 1.2 架构

```
View.query / Object.query
  → ObjectViewBuilder（已有 source_type=KNOWLEDGE_BASE）
  → LLM PlanGenerator 生成 type=KB 的 PlanStep（query + tags）
  → ExecutionObjectConverter 新增 KB → KbExecTask
  → KbExecutor（KnowledgeBaseConnector）HTTP 调用 RAG
  → 结果转为 records → 与 SQL/API 步骤一起参与聚合
```

### 1.3 组件

| 组件 | 说明 |
|------|------|
| **PlanStep type=KB** | `query`（检索文本）、`tags`（dict，field_code→value，LLM 决定传哪些） |
| **KbExecTask** | `datasource_alias`、`query`、`tags`、`output_ref` |
| **KnowledgeBaseConnector** | 配置 RAG 端点（如 `kb_endpoint`），`POST /retrieve` 请求体 `{query, tags}` |
| **KB 结果 → records** | RAG 返回 `[{content, score, metadata?}]`，映射为 `[{field_code: value, ...}]` 供聚合 |

### 1.4 RAG API 约定（可配置）

- **请求**：`POST {kb_endpoint}/retrieve`，Body: `{ "query": str, "tags": dict, "top_k": int? }`
- **响应**：`{ "results": [{ "content": str, "score": float, "metadata": dict? }] }`
- **配置**：`DataSourceConfig` 对 KB 类型扩展 `kb_endpoint`，或单独 `KbSourceConfig`。

### 1.5 错误处理

- RAG 调用失败 → `SqlExecutionError` 或新增 `KbExecutionError`
- 无结果 → 返回空列表，不阻断后续聚合

---

## 2 M5 Skills API

### 2.1 目标与范围

- **目标**：提供 `GET /api/v1/skills/package`，生成供 AI Agent（Cursor、Claude 等）消费的 Skill 包。
- **范围**：#72-74（REST 接口、Skill 包格式、按 view_id / object_ids 过滤）。

### 2.2 架构

```
GET /api/v1/skills/package?view_id=xxx 或 ?object_ids=a,b
  → 校验 X-Tenant-Id
  → 从 OntologyLoader 取 view / objects
  → SkillPackageGenerator 生成包内容
  → 返回 JSON
```

### 2.3 Skill 包格式（JSON）

```json
{
  "version": "1.0",
  "view_id": "VIEW_EMP_OPP",
  "view_name": "员工商机视图",
  "tools": [
    {
      "name": "unified_data_query",
      "description": "自然语言查询员工商机数据",
      "inputSchema": {
        "type": "object",
        "properties": { "question": { "type": "string", "description": "自然语言问题" } },
        "required": ["question"]
      },
      "examples": [
        { "question": "查询邹海天的商机有哪些" },
        { "question": "已签约的商机数量" }
      ]
    },
    {
      "name": "query_bo_by_owner",
      "description": "按负责人查询商机",
      "inputSchema": { ... },
      "examples": [ ... ]
    }
  ]
}
```

- `tools`：unified_data_query + 该 view/objects 下所有 action 工具
- `inputSchema`：与 MCP tools/list 的 inputSchema 一致
- `examples`：每工具 1–3 个示例

### 2.4 接口定义

| 项目 | 说明 |
|------|------|
| 方法 | GET |
| 路径 | `/api/v1/skills/package` |
| 请求头 | X-Tenant-Id（必填） |
| 查询参数 | `view_id` 或 `object_ids`（逗号分隔），至少传其一 |
| 响应 | `Content-Type: application/json`，Body 为上述 JSON |

### 2.5 过滤逻辑

- 传 `view_id`：取该 view 下所有 objects 的 tools
- 传 `object_ids`：仅取指定 objects 的 tools
- 两者都传：view_id 优先

### 2.6 错误处理

- 缺少 X-Tenant-Id → 400
- 未传 view_id 且未传 object_ids → 400
- view_id / object_ids 不存在 → 404 或返回空 tools 数组

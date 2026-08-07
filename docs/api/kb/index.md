# KB API 文档

## KB（知识库动作执行）

| API | Method | Path | Description |
|---|---|---|---|
| [invokeAction](invokeAction.md) | POST | `/api/v1/rpc/kb/invokeAction` | 通过本体加载器 + 执行后端流水线调用 KB 动作（write_*、search_*、merge_write_*、delete_kb_* 等）。 |
| [queryDocumentObjects](queryDocumentObjects.md) | POST | `/api/v1/rpc/kb/queryDocumentObjects` | 按资源、状态、对象类型及处理条件分页查询文档对象。 |
| [queryRelatedDocumentObjects](queryRelatedDocumentObjects.md) | POST | `/api/v1/rpc/kb/queryRelatedDocumentObjects` | 分页查询指定术语的关联关系及两端文档对象。 |
| [getDocumentContentByTermId](getDocumentContentByTermId.md) | POST | `/api/v1/rpc/kb/getDocumentContentByTermId` | 根据术语 ID 获取完整知识文档内容。 |
| [searchKnowledgeFragments](searchKnowledgeFragments.md) | POST | `/api/v1/rpc/kb/searchKnowledgeFragments` | 在指定本体对象范围内检索知识文档分片。 |
| [discoverDocumentObjectsAsync](discoverDocumentObjectsAsync.md) | POST | `/api/v1/rpc/kb/discoverDocumentObjectsAsync` | 提交异步文档对象发现任务。 |
| [enrichDocumentObjectsAsync](enrichDocumentObjectsAsync.md) | POST | `/api/v1/rpc/kb/enrichDocumentObjectsAsync` | 提交异步文档对象整理融合任务。 |

## 通用约定

- 请求体统一为 `{"params": {...}}`，`Content-Type` 为 `application/json`。
- `Beyond-Token` 如有提供会注入调用上下文，供下游服务认证；异步接口还必须提供非空的 `X-Session-Id`。
- 除 `invokeAction` 仅直接读取 `params.base_id` 外，其余接口同时接受 `params.base_id` 和 `params.baseId`；未传时使用 `DEFAULT_BASE_ID`。RPC 分发层还支持 `params.system_code` 作为 `base_id` 的兼容别名，但 `system_code` 与 `base_id` 不能同时传入。
- 成功响应统一为 `{"code": 200, "success": true, "message": "ok", "data": ...}`。
- 参数校验错误返回 `code: 400`，权限错误返回 `code: 403`，未处理异常返回 `code: 500`；错误响应的 `data` 为 `null`。

# API 文档

## KB（知识库动作执行）

| API | Method | Path | Description |
|---|---|---|---|
| [invokeAction](invokeAction.md) | POST | `/api/v1/rpc/kb/invokeAction` | 通过本体加载器 + 执行后端流水线调用 KB 动作（write_*、search_*、merge_write_*、delete_kb_* 等）。 |

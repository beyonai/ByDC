# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Langfuse span metadata 按本体对象分组（`AgentDiag`/`LLMConfig`/`DatacloudConfig`/`DBConfig`/`MinioConfig`/`RedisConfig`/`TermResolution`/`ClarifyContext`/`ActionCall`），支持运维 Agent 语义检索
- 接入 Langfuse 追踪：通过环境变量 `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` 启用，自动追踪 LLM 调用、工具调用和图节点执行
- 知识库对象新增"查询 chunk 内容"虚拟动作
- `build_terms` 支持自动回填 `name_keywords` tsvector 及向量字段，并为所有字段创建 prop 术语
- `build_terms` 支持显式参数覆盖 embedding 回填配置
- `PostgresTermReader` 新增 `delete_scope` 方法
- 知识库与动态表支持虚拟动作的创建与执行
- 本体管理器脚本支持预加载 Embedding 模型配置
- 本体管理器支持挂载资源（mount resource）
- DYNAMIC_TABLE 对象支持 `term_sync` 配置，Action 脚本 insert/update/delete 后自动同步记录到术语库（含 jieba 分词和向量回填）

### Fixed
- 对象字段内联 `term_values` 枚举值在 batch-submit 时未生成术语类型绑定及术语定义写入 OWL 的问题；`build_terms` 现兼容字符串列表格式（`["草稿", "已提交"]`），不再因 `isinstance` 过滤导致枚举值跳过入库
- `HookAwareToolNode` 调用工具时未注入 `InvocationContext` 导致结果文件存储报错的问题
- V0.4 prebuilt 图推送思考步骤时工具名称未翻译为中文显示名的问题
- 动态 Agent 思考过程文字重复推送两遍的问题
- 虚拟工具（`query_*` / `compute_*`）在思考过程中显示技术编码而非中文名称的问题，现显示为 `[内置]查询XX` / `[内置]统计XX`
- OWL 导入时 relation term names 分词缺失及 vocab 序列不同步
- `DynamicQueryExecutor` 不支持 `DYNAMIC_TABLE` source_type 导致工作区动作正式执行报错的问题
- 脚本动作无 `mapping_path` 出参时 `records` 未初始化导致 `UnboundLocalError` 的问题
- 调试与正式执行路径不一致：`run_action_debug` 现在通过 `ScriptExecutor` + `extra_namespace` 注入 DebugMapper，与正式执行共享同一套脚本执行逻辑
- `DYNAMIC_TABLE` 对象有自定义动作时仍注入虚拟动作（`query_*`/`insert_*` 等）与自定义动作冲突的问题
- `ProductionMapper.update_by_id()` 传参格式错误（`record` → `values`+`filters`）导致 `update values must be a non-empty object` 的问题
- 脚本执行失败时完整 traceback 现在输出到服务端日志，便于排查错误原因
- 视图 OWL 生成不准确、非结构化对象缺少参数的问题
- 走服务发现方式的文件上传失败问题
- 查询知识库、知识库目录路径错误的问题

### Changed
- 调用知识服务和 SQLite 统一走服务发现方式，内置对应 backend 和 connector
- Redis 环境变量命名统一为 `REDIS_*` 前缀

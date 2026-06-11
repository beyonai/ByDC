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

### Fixed
- `HookAwareToolNode` 调用工具时未注入 `InvocationContext` 导致结果文件存储报错的问题
- V0.4 prebuilt 图推送思考步骤时工具名称未翻译为中文显示名的问题
- 动态 Agent 思考过程文字重复推送两遍的问题
- 虚拟工具（`query_*` / `compute_*`）在思考过程中显示技术编码而非中文名称的问题，现显示为 `[内置]查询XX` / `[内置]统计XX`
- OWL 导入时 relation term names 分词缺失及 vocab 序列不同步
- 视图 OWL 生成不准确、非结构化对象缺少参数的问题
- 走服务发现方式的文件上传失败问题
- 查询知识库、知识库目录路径错误的问题

### Changed
- 调用知识服务和 SQLite 统一走服务发现方式，内置对应 backend 和 connector
- Redis 环境变量命名统一为 `REDIS_*` 前缀

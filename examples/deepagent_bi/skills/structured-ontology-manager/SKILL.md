---
name: 个人结构化本体管理
description: "对话式结构化个人本体管理：通过自然语言创建、删除个人结构化本体对象和视图，数据存储在个人 SQLite 中"
allowed-tools: execute, read_file
---

# 个人结构化本体管理

通过自然语言对话，管理结构化本体对象和视图。支持创建、删除操作，对象数据持久化到 SQLite。

## 重要：所有操作必须通过注册的 Tool 执行，禁止直接执行脚本文件

## 能力范围

- 查询已有本体对象/视图列表
- 创建本体对象（含字段、术语绑定）
- 创建本体视图（含对象关联关系）
- 删除本体对象（含删表）
- 删除本体视图
- 查询可绑定的术语类型
- 查询术语类型的值列表

## 使用示例

- "帮我创建一个任务管理对象，包含标题、处理人、状态字段"
- "创建一个任务视图，关联任务对象和用户对象"
- "查看我有哪些本体对象"
- "删除任务管理对象"
- "有哪些可用的术语类型？"

## 核心流程

用户意图 → 意图识别 → 信息收集（多轮对话）→ 用户确认 → 执行

## 意图路由（调用对应 Tool，传入 JSON 字符串）

| 用户表达 | 意图 | 调用 Tool | 入参示例 |
|----------|------|-----------|----------|
| 查看/列出 + 对象/视图 | 查询列表 | `list_ontology_resources` | `{"resource_biz_type":"OBJECT"}` |
| 创建/新建 + 对象（收集阶段） | 收集对象信息 | `create_ontology_object` | `{"action":"collect","entity_code":"xxx","entity_name":"xxx","entity_desc":"xxx","fields":[...]}` |
| 确认提交（对象） | 提交对象 | `create_ontology_object` | `{"action":"submit","entity_code":"xxx"}` |
| 创建/新建 + 视图（收集阶段） | 收集视图信息 | `create_ontology_view` | `{"action":"collect","view_code":"xxx","view_name":"xxx"}` |
| 确认提交（视图） | 提交视图 | `create_ontology_view` | `{"action":"submit","view_code":"xxx"}` |
| 删除 + 对象 | 删除对象 | `delete_ontology_object` | `{"resource_id":"xxx","entity_code":"xxx"}` |
| 删除 + 视图 | 删除视图 | `delete_ontology_view` | `{"resource_id":"xxx","view_code":"xxx"}` |
| 查看术语类型 | 查枚举 | `list_ontology_resources` | `{"resource_biz_type":"TERM_TYPE"}` |
| 查看术语值 | 查枚举值 | `get_ontology_detail` | `{"resource_id":"xxx"}` |

## 认证与环境变量

| 变量 | 用途 |
|------|------|
| `BE_DOMAINNAME` | 服务发现，门户服务名称 |
| `BEYOND_TOKEN` | 门户服务 API 认证 |
| `ONTOLOGY_STORE` | 暂存后端：`redis`（默认）或 `local` |
| `REDIS_HOST` | Redis 主机 |
| `REDIS_PORT` | Redis 端口 |
| `REDIS_PASSWORD` | Redis 密码 |

## 参考文档

- [global-reference.md](references/global-reference.md) — 环境变量、认证、输出格式
- [intent-guide.md](references/intent-guide.md) — 意图路由和易混淆场景
- [field-rules.md](references/field-rules.md) — 字段类型与 role/rule_type 规则
- [error-codes.md](references/error-codes.md) — 错误码和调试流程
- [recovery-guide.md](references/recovery-guide.md) — 恢复闭环指南

---
name: ontology-manager
description: "对话式个人本体管理：通过自然语言创建、修改、删除个人本体对象和视图"
allowed-tools: Bash, Read, Write, Edit
---

# ontology-manager

通过自然语言对话，管理个人本体对象和视图。支持创建、修改、删除操作，数据存储在个人 SQLite 中。

## 能力范围

- 创建本体对象（含字段、Action、关系）
- 修改本体对象（增减字段、修改关系/动作）
- 删除本体对象
- 创建本体视图
- 修改本体视图
- 删除本体视图
- 查询已有本体列表

## 使用示例

- "帮我创建一个客户信息对象，包含姓名、手机号、邮箱字段"
- "给客户信息对象添加一个备注字段"
- "删除客户信息对象"
- "创建一个客户分析视图，包含客户信息和商机对象的字段"
- "修改客户分析视图，去掉商机金额字段"
- "查看我有哪些本体对象"

## 核心流程

```
用户意图 → 意图识别 → 信息收集（多轮对话）→ 用户确认 → 执行
```

执行步骤（对象创建为例）：
1. 校验 JSON（schema_validator）
2. 生成 OWL 文件集（owl_builder）
3. 打包 zip（owl_packager）
4. 上传 OWL（OWL 管理 API）
5. 建表（SQLite API）

## 认证

所有认证信息从进程环境变量自动读取，无需用户提供。脚本运行在本地文件系统，**不是沙箱或容器环境**，可以直接执行：

| 变量 | 用途 |
|------|------|
| `BEYOND_TOKEN` | OWL 管理 API 认证 |
| `USER_CODE` | 当前用户编码，SQLite 数据隔离 key |
| `OPENCLAW_GATEWAY_TOKEN` | SQLite API 认证（固定值 ztesoft） |
| `BYAI_BASE_URL` | OWL 管理 API 基础地址 |
| `SQLITE_API_URL` | SQLite API 地址 |

## 执行方式

本 skill 的操作通过以下专用 Tool 执行（无需 shell 命令）：

| Tool | 用途 |
|------|------|
| `create_ontology_object` | 创建本体对象 |
| `modify_ontology_object` | 修改本体对象 |
| `delete_ontology_object` | 删除本体对象 |
| `create_ontology_view` | 创建本体视图 |
| `modify_ontology_view` | 修改本体视图 |
| `delete_ontology_view` | 删除本体视图 |
| `list_ontology_resources` | 查询本体列表 |

**禁止**使用 `execute`/`bash`/`shell` 工具调用脚本，直接调用上述 Tool。



- [global-reference.md](references/global-reference.md) — 环境变量、认证、输出格式
- [intent-guide.md](references/intent-guide.md) — 意图路由和易混淆场景
- [field-rules.md](references/field-rules.md) — 字段类型规则（DIMENSION/MEASURE）
- [error-codes.md](references/error-codes.md) — 错误码和调试流程
- [recovery-guide.md](references/recovery-guide.md) — 恢复闭环指南

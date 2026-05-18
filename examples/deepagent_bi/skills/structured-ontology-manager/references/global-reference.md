# 全局参数、认证、输出格式

## 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `BE_DOMAINNAME` | 服务发现，门户服务名称 | 必填 |
| `BEYOND_TOKEN` | 门户服务 API 认证 Token | 必填 |
| `ONTOLOGY_STORE` | 暂存后端：`redis`（默认）或 `local` | `redis` |
| `ONTOLOGY_REDIS_HOST` | Redis 主机 | `localhost` |
| `ONTOLOGY_REDIS_PORT` | Redis 端口 | `6379` |
| `ONTOLOGY_REDIS_DB` | Redis DB | `0` |
| `ONTOLOGY_REDIS_PASSWORD` | Redis 密码 | 空 |
| `DATACLOUD_GATEWAY_REDIS_HOST` | 服务发现 Redis 主机 | `localhost` |
| `DATACLOUD_GATEWAY_REDIS_PORT` | 服务发现 Redis 端口 | `6379` |
| `PERSONAL_SQLITE_PATH` | SQLite 文件路径（本地模式） | `~/.ontology_workspace/personal.db` |

## 认证方式

所有门户服务请求通过 `Beyond-Token` Header 传递认证 Token。
Token 优先从 `BEYOND_TOKEN` 环境变量读取，其次从 `get_current_context().token` 获取。

## 输出格式

所有脚本统一输出 JSON 到 stdout：

```json
// 成功
{"ok": true, "data": [...]}

// 失败
{"ok": false, "error": "错误描述", "missing": ["缺失字段"]}
```

## session_id 说明

- 多用户场景：`session_id` 来自 Agent 上下文，保证多用户并发隔离
- 本地开发模式（`ONTOLOGY_STORE=local`）：`session_id` 可省略，key 退化为 `entity_code`
- 同一用户的多轮对话必须传相同的 `session_id`，否则暂存状态无法关联

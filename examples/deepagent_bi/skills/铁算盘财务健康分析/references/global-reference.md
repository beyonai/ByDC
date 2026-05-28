# 全局参数说明

## 环境变量

| 变量 | 是否必需 | 说明 |
|------|----------|------|
| `BEYOND_TOKEN` | ✅ | 门户服务认证 Token |
| `USER_CODE` | ✅ | 当前用户编码 |
| `BE_DOMAINNAME` | ✅ | 门户服务名称，默认 `ByaiService` |
| `REDIS_HOST` | ✅ | 服务发现 Redis 主机 |
| `REDIS_PORT` | ✅ | Redis 端口，默认 `6379` |
| `REDIS_DATABASE` | ❌ | Redis DB，默认 `0` |
| `REDIS_PASSWORD` | ✅ | Redis 密码 |
| `REDIS_USERNAME` | ❌ | Redis 用户名，默认 `default` |
| `DATACLOUD_LLM_MODEL` | ✅ | 数据查询 LLM 模型编码 |

## 快速检查

```bash
env | grep -E 'BEYOND_TOKEN|USER_CODE|BE_DOMAINNAME|REDIS_HOST|DATACLOUD_LLM_MODEL'
```

## 输出格式

所有脚本统一输出 JSON 到 stdout：

```json
// 成功
{"ok": true, "report": "## #铁算盘 财务健康报告\n..."}

// 失败
{"ok": false, "error": "错误描述"}
```

## 接力模式

多人格接力时，前一个 skill 的 `report` 字段作为下一个 skill 入参的 `context` 传入：

```json
{"question": "从战略角度看这些商机", "context": "<上一个skill的report内容>"}
```

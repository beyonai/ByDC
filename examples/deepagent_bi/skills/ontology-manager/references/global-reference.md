# 全局参考

## 环境变量

所有认证信息从进程环境变量自动读取，无需用户提供：

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `BEYOND_TOKEN` | OWL 管理 API 认证 Token | eyJhbGci... |
| `USER_CODE` | 当前用户编码，SQLite 数据隔离 key | 0027024630 |
| `BEYOND_SESSION` | 会话 ID（备用） | 7911f115-... |
| `OPENCLAW_GATEWAY_TOKEN` | SQLite API Token，固定值 | ztesoft |
| `BYAI_BASE_URL` | OWL 管理 API 基础地址 | http://10.10.168.203:8080/byaiService |
| `SQLITE_API_URL` | SQLite API 地址 | http://10.10.168.203:51919/plugins/byclaw-sqlite/sqlExecute |

## 输出格式

所有脚本统一输出 JSON 到 stdout：

**成功**：
```json
{"ok": true, "entity_code": "by_xxx", "resourceId": "10000030"}
```

**失败**：
```json
{"ok": false, "error": "错误描述"}
```

**dry-run**：
```json
{"ok": true, "dry_run": true, "entity_code": "by_xxx", "field_count": 3}
```

## --dry-run 模式

所有脚本支持 `--dry-run` 参数，预览操作但不实际执行：

```bash
python create_object.py --dry-run '{"entity_name": "测试对象", ...}'
python delete_object.py --dry-run 10000030 by_test
```

## SDK 依赖

脚本依赖 `by-datacloud` SDK，需确保已安装：

```bash
pip install by-datacloud
# 或
uv add by-datacloud
```

SDK 提供：
- `datacloud_data_sdk.ontology.utils` — 中文转拼音
- `datacloud_data_sdk.ontology.schema_validator` — JSON 校验
- `datacloud_data_sdk.ontology.owl_builder` — JSON → OWL
- `datacloud_data_sdk.ontology.owl_packager` — OWL → zip

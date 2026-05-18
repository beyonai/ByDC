# 错误码与调试

## 常见错误

| 错误码/关键词 | 含义 | 处理方式 |
|--------------|------|---------|
| `SDK 未安装` | by-datacloud 包未安装 | `pip install by-datacloud` 或 `uv add by-datacloud` |
| `entity_name: 必填` | 对象名称为空 | 引导用户提供对象名称 |
| `data_type: 不合法` | 字段类型不在枚举范围 | 参考 field-rules.md 的合法类型列表 |
| `rule_type 必须搭配` | role 与 rule_type 不匹配 | 参考 field-rules.md 的合法组合表 |
| `API error` | OWL 管理 API 返回错误 | 检查 BEYOND_TOKEN 是否有效 |
| `SQLite API error` | SQLite API 返回错误 | 检查 SQLITE_API_URL 和 OPENCLAW_GATEWAY_TOKEN |
| `资源不存在` | resourceId 无效 | 先用 list_resources.py 确认资源存在 |
| `已有相同编码...在企业的视图下` | ownerType 冲突 | 视图 code 已在企业下，需换一个 view_code |

## 调试步骤

1. **检查环境变量**：确认 BEYOND_TOKEN、USER_CODE、SQLITE_API_URL 已设置
2. **验证连通性**：
   ```bash
   # 测试 SQLite API
   curl -X POST $SQLITE_API_URL \
     -H "Authorization: Bearer ztesoft" \
     -H "Content-Type: application/json" \
     -d '{"sql":"SELECT 1","user_code":"dev"}'

   # 测试 OWL API
   curl -X POST $BYAI_BASE_URL/auth/privilegeGrant/listResourceUseAuth \
     -H "Beyond-Token: $BEYOND_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"pageNum":1,"pageSize":5,"ownerType":"personal","resourceStatus":"2","resourceBizTypeList":["OBJECT"]}'
   ```
3. **使用 --dry-run**：先用 dry-run 模式验证参数，再实际执行
4. **查看资源列表**：`python list_resources.py --type OBJECT`

## 恢复策略

| 场景 | 处理方式 |
|------|---------|
| OWL 上传成功但建表失败 | 重新执行 create_object.py（CREATE TABLE IF NOT EXISTS 幂等） |
| 建表成功但 OWL 上传失败 | 重新执行 create_object.py（OWL 上传覆盖幂等） |
| 修改时 ALTER TABLE 失败 | 手动执行 ALTER TABLE 补齐，或重新执行 modify_object.py |
| 删除时 OWL 删除成功但 DROP TABLE 失败 | 手动执行 `DROP TABLE IF EXISTS {entity_code}` |

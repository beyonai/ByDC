# 恢复闭环指南

## OWL 上传成功但建表失败

**现象**：create_object.py 返回 `{"ok": false, "error": "SQLite API error: ..."}`，但 OWL 已上传成功。

**处理**：
1. 重新执行 create_object.py（`CREATE TABLE IF NOT EXISTS` 幂等，不会重复建表）
2. 或手动执行建表 SQL：
   ```bash
   curl -X POST $SQLITE_API_URL \
     -H "Authorization: Bearer ztesoft" \
     -H "Content-Type: application/json" \
     -d '{"sql":"CREATE TABLE IF NOT EXISTS by_xxx (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)","user_code":"dev"}'
   ```

## 建表成功但 OWL 上传失败

**现象**：SQLite 表已创建，但 OWL 上传返回错误。

**处理**：
1. 重新执行 create_object.py（OWL 上传覆盖幂等，相同内容重复上传返回"未检测到内容差异"）
2. 如果 OWL 持续失败，检查 BEYOND_TOKEN 是否过期

## 修改操作部分失败

- OWL 上传成功但 ALTER TABLE 失败 → 重新执行 modify_object.py
- ALTER TABLE 成功但 OWL 上传失败 → 重新执行 modify_object.py

## 删除操作部分失败

- OWL 删除成功但 DROP TABLE 失败 → 手动执行 `DROP TABLE IF EXISTS {entity_code}`
- DROP TABLE 成功但 OWL 删除失败 → 重新执行 delete_object.py（delete_resource 幂等）

## 用户取消操作

任何步骤前用户说"取消"，直接退出，不执行任何操作。
已执行的步骤不回滚（OWL 上传和建表均为幂等操作）。

## 视图 ownerType 冲突

**现象**：上传视图时返回"已有相同编码（xxx）的视图是在企业的视图下"。

**处理**：
1. 提示用户该 view_code 已被企业视图占用
2. 引导用户修改视图名称，系统会生成新的 view_code
3. 或手动指定一个不冲突的 view_code

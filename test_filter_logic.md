# ext_attrs 过滤功能验证

## 代码位置
`packages/datacloud-platform/src/datacloud_platform/api/routers/rpc/handlers/term.py`

## 过滤逻辑（第 417-432 行）

```python
# 如果设置了过滤条件，检查是否匹配
if filter_kb_id or filter_kb_file_path:
    if not ext_attrs or not isinstance(ext_attrs, dict):
        continue  # 没有 ext_attrs，跳过此术语

    # 检查 kb_id 过滤
    if filter_kb_id:
        term_kb_id = ext_attrs.get("kb_id")
        if str(term_kb_id) != str(filter_kb_id):
            continue

    # 检查 kb_file_path 过滤
    if filter_kb_file_path:
        term_kb_file_path = ext_attrs.get("kb_file_path")
        if term_kb_file_path != filter_kb_file_path:
            continue
```

## 功能说明

1. **参数接收**（第 343-344 行）
   - `kb_id`: 从 `params.get("kb_id")` 获取
   - `kb_file_path`: 从 `params.get("kb_file_path")` 获取

2. **过滤条件**
   - 如果设置了任一过滤参数，则进入过滤模式
   - 没有 `ext_attrs` 的术语直接跳过
   - `kb_id` 比较时会转换为字符串（支持数字和字符串格式）
   - `kb_file_path` 进行严格字符串匹配

3. **API 调用示例**
   ```json
   POST /api/v1/rpc/term/getKnowledgeByTermWord
   {
     "params": {
       "keywords": ["byDC"],
       "searchLevel": "1",
       "kb_id": "78",
       "kb_file_path": "/Product/byDC.md"
     }
   }
   ```

## 预期行为

查询 `term_name=byDC` 时：
- 不带过滤参数：返回所有名为 "byDC" 的术语
- 带过滤参数 `kb_id=78, kb_file_path=/Product/byDC.md`：
  - 只返回 `ext_attrs` 中同时满足 `kb_id="78"` 和 `kb_file_path="/Product/byDC.md"` 的术语
  - 其他术语会在第 420/426/432 行被 `continue` 跳过

## 验证方法

使用 HTTP 客户端（如 curl、Postman）调用 API：
```bash
curl -X POST http://localhost:8000/api/v1/rpc/term/getKnowledgeByTermWord \
  -H "Content-Type: application/json" \
  -d '{
    "params": {
      "keywords": ["byDC"],
      "searchLevel": "1",
      "kb_id": "78",
      "kb_file_path": "/Product/byDC.md"
    }
  }'
```

预期结果：
- 如果数据库中存在符合条件的术语，返回该术语及其 `kb_id`、`kb_file_path` 字段
- 如果不存在符合条件的术语，返回 `{"error": "No term found for keyword"}`

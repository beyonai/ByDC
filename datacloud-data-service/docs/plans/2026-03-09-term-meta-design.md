# termMeta 转换与术语 API 加载设计

**日期**: 2026-03-09  
**目标**: 本体 JSON 使用 termMeta 格式，转换为内部模型并支持术语 API 查询加载。

---

## 1. 需求摘要

| 项目 | 说明 |
|------|------|
| 本体 JSON 格式 | termMeta: { datasetId, termMasterType, termTypeCode, termField } |
| 内部模型 | OntologyField、OntologyActionParam、ObjectViewField、ObjectViewFunctionParam |
| 转换 | term_set、term_type、dataset_id |
| 术语加载 | POST {ZNT_SERVER}/core/term/queryStandardTerm |
| termTypeCode | 对应 term_set 点前的部分（即 "user.code" 中的 "user"），作为 API 的 termType 参数 |
| keyword | 可为空；termMasterType="list" 时可通过 keyword 搜索 |

---

## 2. termMeta 转换规则

### 2.1 转换映射

| termMeta 字段 | 转换结果 |
|---------------|----------|
| termTypeCode + termField | term_set = f"{termTypeCode}.{termField}" |
| termMasterType | term_type = "enum" if "dict" else "lookup" |
| datasetId | dataset_id（整数） |

### 2.2 解析优先级

- 有 termMeta → 按上表转换
- 无 termMeta 有 term_set → 仅 term_set，term_type=None，dataset_id=None
- 两者都有 → termMeta 优先

### 2.3 termMasterType → termType

| termMasterType | term_type（给模型） |
|----------------|---------------------|
| "dict" | "enum" |
| "list" | "lookup" |

---

## 3. 模型变更

| 模型 | 新增字段 |
|------|----------|
| OntologyField | term_type: str \| None = None，dataset_id: int \| None = None |
| OntologyActionParam | 同上 |
| ObjectViewField | 同上 |
| ObjectViewFunctionParam | 同上 |

保留 term_set。

---

## 4. 术语 API 设计

### 4.1 配置

| 环境变量 | 说明 |
|----------|------|
| DC_ZNT_SERVER | 术语服务基础地址，如 `https://api.example.com` |

完整 URL：`{DC_ZNT_SERVER}/core/term/queryStandardTerm`

### 4.2 请求参数

| 参数 | 来源 | 说明 |
|------|------|------|
| datasetIds | termMeta.datasetId | 转为字符串数组，如 ["752562121390277"] |
| termType | termTypeCode（term_set 逗号前） | 如 "user.code" → "user" |
| keyword | 可选 | 空查全部；termMasterType="list" 时可通过 keyword 搜索 |
| queryType | 固定或可配置 | "fullTextRecall" 或 "exactMatch" |
| topK | 默认 100 | 返回条数 |

### 4.3 响应映射

| API 字段 | TermEntry |
|----------|-----------|
| termCode | code |
| termName | label |
| synonyms | aliases（按分隔符拆分） |

### 4.4 keyword 使用

- **get_available_values**：keyword 为空，加载全部
- **resolve_code(value)**：termMasterType="list" 时，keyword=value 用于搜索匹配

---

## 5. 修改点

| 文件 | 修改 |
|------|------|
| ontology/loader.py | _parse_fields、_parse_actions：解析 termMeta，填充 term_set、term_type、dataset_id |
| ontology/models.py | OntologyField、OntologyActionParam 增加 term_type、dataset_id |
| plan/models.py | ObjectViewField、ObjectViewFunctionParam 增加 term_type、dataset_id |
| plan/object_view_builder.py | 构建时传入 term_type、dataset_id |
| plan/query_plan_generator.py | _serialize_param：优先用 term_type，无则用 term_loader 推断 |
| ontology/term_loader.py | 扩展：支持 API 模式，get_available_values/resolve_code 可调 API |
| config.py | 增加 znt_server: str |
| .env.example | 增加 DC_ZNT_SERVER |

---

## 6. 字段名兼容（可选）

若本体 JSON 使用 `properties` / `property_code`：

- `raw_fields = obj.get("fields", obj.get("properties", []))`
- `field_code = f.get("field_code", f.get("property_code"))`

---

## 7. 错误处理

- termMeta 缺 termTypeCode 或 termField：不推导 term_set，term_set=None
- datasetId 缺失或非法：dataset_id=None
- 术语 API 调用失败：记录日志，回退到内存 mapping 或返回空

---

## 8. 验收标准

1. 本体 JSON 含 termMeta 时，解析后 term_set、term_type、dataset_id 正确
2. 序列化给模型时，term_type 正确为 enum/lookup
3. term_type=enum 时，可调用术语 API 获取 termLabels
4. term_type=lookup 且 resolve_code 时，可通过 keyword 搜索
5. 无 termMeta 仅有 term_set 时，行为与现有一致

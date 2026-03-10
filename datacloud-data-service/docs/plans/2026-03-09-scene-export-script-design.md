# 场景完整 JSON 导出脚本设计

**日期**: 2026-03-09  
**目标**: 根据场景定义和 objects_registry，生成包含对象、函数、关联关系的完整自包含 JSON

---

## 1. 输出格式

```json
{
  "view_id": "scene_01_data_analysis",
  "view_name": "在线查数分析场景",
  "description": "销售数据分析场景，支持简单查询、跨库联合检索、非结构化融合检索",
  "functions": [...],
  "objects": [...],
  "relations": [...]
}
```

- 顶层保留场景元信息：`view_id`、`view_name`、`description`
- `functions`：仅包含被场景内对象引用的函数
- `objects`：仅包含 `object_ids` 中的对象
- `relations`：仅包含 source/target 均在 `object_ids` 内的关系

---

## 2. 过滤逻辑

| 节点 | 过滤规则 |
|------|----------|
| **objects** | `object_code` ∈ `scene.object_ids` |
| **relations** | `source_class` ∈ object_ids 且 `target_class` ∈ object_ids |
| **functions** | `function_code` ∈ 所有 objects 的 actions[].function_refs 并集 |

---

## 3. 脚本接口

```bash
python scripts/export_scene_json.py \
  --scene resources/ontology/crm_demo/scene_01_data_analysis.json \
  --registry resources/ontology/crm_demo/objects_registry.json \
  --output resources/ontology/crm_demo/scene_01_data_analysis_full.json
```

或使用默认路径（scene 与 registry 同目录）：

```bash
python scripts/export_scene_json.py \
  --scene scene_01_data_analysis.json \
  --output scene_01_data_analysis_full.json
```

---

## 4. 实现要点

1. **函数收集**：遍历每个 object 的 `actions`，收集 `function_refs` 中的 `function_code`，去重
2. **自包含**：输出 JSON 可被 OntologyLoader 直接 `load_from_content()` 使用
3. **object_ids 顺序**：输出 objects 顺序与 scene 的 `object_ids` 一致（可选）
4. **错误处理**：object_ids 中若存在 registry 中不存在的 object_code，记录警告并跳过

---

## 5. 文件位置

- 脚本：`datacloud-data-service/scripts/export_scene_json.py`
- 输出示例：`resources/ontology/crm_demo/scene_01_data_analysis_full.json`

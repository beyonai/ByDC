# 非结构化对象实例检索

```
POST /api/v1/rpc/search/searchObjectInstancesUnstructured
```

通过自然语言句子或词语检索对象实例。支持两种输入模式（根据传参自动推断）：

- **sentence 模式**：传入 `query`（自然语言句子），jieba 分词后多 token 匹配 + RRF(k=60) 双路融合
- **word_batch 模式**：传入 `queries`（词语列表），每个词独立检索 + `asyncio.gather` 并发 chunk 搜索，返回按词分组的批量结果

---

## RPC Payload

所有参数放在 `params` 内。

```json
{
  "params": {
    "base_id": "BYCLAW_DATACLOUD",
    "object_codes": null,
    "query": "帮我查一下张三相关的商机",
    "queries": ["OCR", "Agent", "Tool"],
    "top_k": 20,
    "enable_chunk_recall": true
  }
}
```

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `base_id` | string | Yes | — | 本体库 ID。 |
| `object_codes` | string[] \| null | No | `null` | 对象类型编码列表。`null` 表示不限类型跨全类型检索，`[]` 返回空结果。 |
| `query` | string | 条件 | — | **sentence 模式**：自然语言查询文本。与 `queries` 二选一。 |
| `queries` | string[] | 条件 | — | **word_batch 模式**：词语列表。与 `query` 二选一，优先 `queries`。 |
| `top_k` | integer | No | `20` | 每路返回的最大结果数。 |
| `enable_chunk_recall` | boolean | No | `true` | 是否启用路2（KB chunk 语义搜索）。 |

> 输入模式推断：传 `queries` → `word_batch`；传 `query` → `sentence`；都不传返回空。

---

## 双路召回 + RRF 融合

```
输入文本
  │
  ├─ 路1（术语实例检索）
  │   object_codes 指定 → search_terms_batch(term_type_codes=object_codes) 原生 IN 过滤
  │   object_codes=None  → search_terms_batch(term_type_codes=None) 跨全类型
  │
  └─ 路2（KB Chunk 间接检索）
      object_codes 指定 → EntityStore → _collect_kb_ids 收集 kb_ids → chunk search
      object_codes=None  → 不执行路2
      chunk → filePath 聚合 → resource_id → term_tags.kb_resource_id 匹配
  │
  ▼
RRF(k=60) 融合 → [{instance_id, instance_code, instance_name, object_code, file_name, score}, ...]
```

### 降级策略

| 条件 | 行为 |
|---|---|
| `enable_chunk_recall=false` | 仅路1 |
| `object_codes=None` | 仅路1，路2不执行 |
| KB chunk 搜索异常 | warning 日志 + 仅路1 |
| 分词器 bimm 不可用 | 纯 jieba 分词 |

---

## Response Body

返回 `{keyword: [hit, ...]}` 格式，key 为查询词（sentence 模式时 key 为原始 query 文本）。

```json
{
  "code": 200,
  "success": true,
  "message": "ok",
  "data": {
    "OCR": [
      {
        "instance_id": "b691924f-9efb-45ec-999c-a2fc4ec01d18",
        "instance_code": "OCR 组织一致性调节器机制",
        "instance_name": "OCR 组织一致性调节器机制",
        "object_code": "Methodology",
        "file_name": "/Methodology/OCR组织一致性调节器机制.md",
        "score": 0.0164
      }
    ],
    "Agent": [
      {
        "instance_id": "1954df64-e0c7-4f56-9816-b2e87ad4e0d0",
        "instance_code": "Agent",
        "instance_name": "Agent",
        "object_code": "Concept",
        "file_name": "/Concept/Agent.md",
        "score": 0.0159
      }
    ]
  }
}
```

### Hit 字段

| Field | Type | Description |
|---|---|---|
| `instance_id` | string | 实例 ID（term_id，全局唯一）。 |
| `instance_code` | string | 实例编码（term_code，业务编码）。 |
| `instance_name` | string | 实例名称（term_name）。 |
| `object_code` | string | 所属对象类型编码（term_type / object_code）。 |
| `file_name` | string \| null | 对应知识库文件路径（ext_attrs.kb_file_path）。`null` 表示无文件关联。 |
| `score` | float | 检索分数。双路为 RRF(k=60) 融合分数，单路为该路原始分数。 |

---

## Example

### 1. sentence 模式 — 自然语言句子

```bash
curl -s http://localhost:8088/api/v1/rpc/search/searchObjectInstancesUnstructured \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "params": {
      "base_id": "BYCLAW_DATACLOUD",
      "object_codes": null,
      "query": "帮我查一下张三相关的商机",
      "top_k": 10,
      "enable_chunk_recall": true
    }
  }'
```

### 2. word_batch 模式 — 多词语批量

```bash
curl -s http://localhost:8088/api/v1/rpc/search/searchObjectInstancesUnstructured \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "params": {
      "base_id": "BYCLAW_DATACLOUD",
      "object_codes": null,
      "queries": ["OCR", "Agent", "Tool"],
      "top_k": 3,
      "enable_chunk_recall": false
    }
  }'
```

### 3. 指定对象类型

```bash
curl -s http://localhost:8088/api/v1/rpc/search/searchObjectInstancesUnstructured \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "params": {
      "base_id": "BYCLAW_DATACLOUD",
      "object_codes": ["by_opportunity"],
      "query": "张三的商机",
      "top_k": 5,
      "enable_chunk_recall": true
    }
  }'
```

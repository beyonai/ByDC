# 枚举非结构化对象实例（度数条件过滤 + 相似度排序）

```
POST /api/v1/rpc/search/enumerateObjectInstances
```

**枚举型**接口：按「对象实例之间的关系满足出度/入度对比条件」+「对象类型或知识库范围」分页枚举**全部**符合条件的非结构化对象实例，可叠加可选**语义相似度排序**（`sort`）在候选集内重排。与检索接口（[searchObjectInstancesUnstructured](searchObjectInstancesUnstructured.md)）本质不同：

| 维度 | 检索接口 | 枚举接口（本接口） |
|---|---|---|
| 语义 | 关键词 → RRF 排序截断 | 确定性条件过滤（可叠加相似度重排） |
| totalCount | 不诚实（RRF rank 依赖） | **诚实**（同条件 COUNT，排序不截断候选集） |
| 分页稳定性 | 跨页顺序不保证 | **稳定**（确定性排序 + term_id tie-break） |

条件与排序体系均为**可插拔框架**：`filters` 数组 + 注册表（当前仅 `degree` 一个类型）、`sort` 规格 + 注册表（当前仅 `similarity` 一个依据），未来新增条件类型/排序依据只需在 knowledge 层注册表加一条目，接口形状 / RPC handler / 返回模型零改动。

---

## RPC Payload

所有参数放在 `params` 内。

```json
{
  "params": {
    "base_id": "BYCLAW_DATACLOUD",
    "object_codes": ["Event", "Document"],
    "kb_resource_ids": ["10000383"],
    "filters": [
      {
        "type": "degree",
        "params": {
          "metric": "out_minus_in",
          "op": "gte",
          "value": 0
        }
      }
    ],
    "sort": {
      "by": "similarity",
      "params": {
        "query": "退货单"
      }
    },
    "page": 1,
    "pageSize": 20
  }
}
```

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `base_id` | string | Yes | — | 本体库 ID。 |
| `object_codes` | string[] \| null | No | — | 对象类型范围。**全空（与 `kb_resource_ids` 都为空）→ 返回空结果**；显式传参尊重输入不校验。 |
| `kb_resource_ids` | string[] \| null | No | — | 知识库资源范围（过滤 `term.ext_attrs->>'kb_resource_id'`）。与 `object_codes` 同时给时取 **AND 交集**。 |
| `filters` | object[] \| null | No | — | 条件数组（v1 多条件之间 AND）。`filters` **不代替范围**：范围全空时即使有 filters 也返回空。 |
| `sort` | object \| null | No | — | 排序规格（当前仅 `similarity`）。**原样透传不解析**；候选集内重排，不截断，total 仍诚实。`sort` 不代替范围。 |
| `page` | integer | No | `1` | 页码，1-based，钳制 `>=1`。 |
| `pageSize` | integer | No | `20` | 每页条数，钳制 `>=1`。 |

> 范围语义：`object_codes` 与 `kb_resource_ids` 至少给一个才执行查询；单维给按对应维度过滤，双维给 AND。按 `kb_resource_id` 过滤天然排除无 KB 归属的结构化术语。

---

## filters — degree（度数对比条件）

度数只统计**实例之间的关系**：`term_relation` 中 `source_term_id` 与 `target_term_id` 均非空（实例级边）且 `relation_category = 'BUSINESS'` 的行；自环（source=target）计入出度与入度各一次；度数基于**全图**（不因范围过滤截断邻域）。

### Schema

```json
{
  "type": "degree",
  "params": {
    "metric": "out_minus_in",
    "op": "gte",
    "value": 0
  }
}
```

### params 字段

| Field | Type | Allowed | Description |
|---|---|---|---|
| `metric` | string | `out_minus_in` / `out_ratio_in` / `out` / `in` | 度量：出度减入度 / 出度比入度 / 出度 / 入度。非法值返回 400。 |
| `op` | string | `gt` / `gte` / `lt` / `lte` / `eq` | 比较操作符。非法值返回 400。 |
| `value` | number | — | 对比阈值。 |

**常见用法**：
- 出度 > 入度（影响力节点）→ `{"metric": "out_minus_in", "op": "gt", "value": 0}`
- 出度 ≥ 2×入度（强发散节点）→ `{"metric": "out_ratio_in", "op": "gte", "value": 2}`
- 出度 ≥ 5 → `{"metric": "out", "op": "gte", "value": 5}`

> **比值除零语义**：`out_ratio_in` 且 `in=0` 时——`out>0` → 比值视为 +∞（`gt`/`gte` 恒通过，`lt`/`lte` 恒不通过）；`out=0 且 in=0` → 无定义，该实例不参与比值条件。

---

## sort — similarity（语义相似度排序）

可选排序规格：按 `query` 对**候选集**（`object_codes` / `kb_resource_ids` / `filters` 过滤后）做语义相似度重排，随后照常分页。适合「先按度数等条件圈定范围，再按语义相关度取 TOP」的场景。

### Schema

```json
{
  "by": "similarity",
  "params": {
    "query": "退货单"
  }
}
```

### params 字段

| Field | Type | Allowed | Description |
|---|---|---|---|
| `query` | string | — | 语义查询串。空串 / 缺省 → 退化 `term_id ASC`（无排序）。非字符串返回 400。 |

### 语义（钉死）

- **候选集内重排，不截断**：排序本身无 LIMIT，仅分页 LIMIT/OFFSET 生效；`total` 仍是同条件 COUNT 的诚实值。
- **排序键** = 实例（term）下全部 name 的**最佳相似度** `MAX(1 - (name_embedding <=> :vector))`（余弦公式与检索接口同形）；`name_embedding` 为 NULL 的实例排尾部（`NULLS LAST`）。
- **双键稳定排序**：分数 `DESC` + `term_id ASC` tie-break，跨页不重不漏。
- **Embedding 不可用自动降级**：Embedding API 未配置/调用失败 → 静默降级 BM25 单字（`ts_rank_cd(name_keywords)`），**不 500**。
- **显式 `sort` 优先**：给定 `sort` 时覆盖 degree filter 的隐式排序；两者皆无 → `term_id ASC`。
- **错误映射**：未知 `by` / `params` 非 dict / `query` 非字符串 → knowledge 层校验抛错 → 400 `invalid_params`。

---

## Response Body

```json
{
  "code": 200,
  "success": true,
  "message": "ok",
  "data": {
    "items": [
      {
        "instance_id": "375434d2-de06-44de-9a1d-5957f84008c9",
        "instance_code": "数据本体论周报_2026年7月13-20日--20260723T062349Z-a0d606",
        "instance_name": "数据本体论周报_2026年7月13-20日--20260723T062349Z-a0d606",
        "object_code": "Event",
        "file_name": "/Event/数据本体论周报_2026年7月13-20日--20260723T062349Z-a0d606.md",
        "kb_resource_id": "10000383",
        "kb_id": "27",
        "out_degree": 1,
        "in_degree": 0
      }
    ],
    "total": 57,
    "page": 1,
    "pageSize": 20
  }
}
```

### 字段

| Field | Type | Description |
|---|---|---|
| `items` | object[] | `ObjectInstanceListItem` 数组（9 字段，见下）。 |
| `total` | integer | **诚实总数**（与 items 同条件的 COUNT，不含分页截断）。 |
| `page` | integer | 当前页码。 |
| `pageSize` | integer | 每页条数。 |

### ObjectInstanceListItem

| Field | Type | Description |
|---|---|---|
| `instance_id` | string | 实例 ID（term_id，全局唯一）。 |
| `instance_code` | string | 实例编码（term_code）。 |
| `instance_name` | string | 实例名称（term_name）。 |
| `object_code` | string | 所属对象类型编码（term_type_code）。 |
| `file_name` | string \| null | 知识库文件路径（ext_attrs.kb_file_path）。 |
| `kb_resource_id` | string \| null | 知识库资源 ID（ext_attrs.kb_resource_id）。 |
| `kb_id` | string \| null | 知识库内部 ID。 |
| `out_degree` | integer | 出度（BUSINESS 实例级边数）。 |
| `in_degree` | integer | 入度（BUSINESS 实例级边数）。 |

### 排序规则

优先级（高 → 低）：

1. 显式 `sort`（`_SORT_REGISTRY`，当前仅 `similarity`）→ 分数降序 + `term_id` 升序
2. `filters` 含 `degree` 型 → 按该 `metric` 对应度量值**降序** + `term_id` 升序（tie-break）
3. 无显式 sort / 无 degree filter（纯范围）→ 按 `term_id` 升序

三种排序均为确定性稳定排序，跨页不重不漏。

---

## Example

### 1. 出度 ≥ 入度（Event 类型）

```bash
curl -s http://localhost:8088/api/v1/rpc/search/enumerateObjectInstances \
  -X POST -H "Content-Type: application/json" \
  -H "Beyond-Token: $BEYOND_TOKEN" \
  -d '{
    "params": {
      "object_codes": ["Event"],
      "filters": [
        {"type": "degree", "params": {"metric": "out_minus_in", "op": "gte", "value": 0}}
      ],
      "page": 1,
      "pageSize": 20
    }
  }'
```

### 2. 限定知识库范围

```bash
curl -s http://localhost:8088/api/v1/rpc/search/enumerateObjectInstances \
  -X POST -H "Content-Type: application/json" \
  -H "Beyond-Token: $BEYOND_TOKEN" \
  -d '{
    "params": {
      "kb_resource_ids": ["10000383"],
      "page": 1,
      "pageSize": 20
    }
  }'
```

### 3. 范围全空 → 空结果

```bash
curl -s http://localhost:8088/api/v1/rpc/search/enumerateObjectInstances \
  -X POST -H "Content-Type: application/json" \
  -H "Beyond-Token: $BEYOND_TOKEN" \
  -d '{
    "params": {
      "filters": [
        {"type": "degree", "params": {"metric": "out_minus_in", "op": "gte", "value": 0}}
      ],
      "page": 1,
      "pageSize": 5
    }
  }'
# → {"code":200,"success":true,"message":"ok","data":{"items":[],"total":0,"page":1,"pageSize":5}}
```

### 4. 度数圈定 + 语义相似度排序

「出度 ≥ 入度」圈定候选集，再按 query「退货单」相似度降序取 TOP 20（Embedding 缺失时自动降级 BM25 单字，不 500）：

```bash
curl -s http://localhost:8088/api/v1/rpc/search/enumerateObjectInstances \
  -X POST -H "Content-Type: application/json" \
  -H "Beyond-Token: $BEYOND_TOKEN" \
  -d '{
    "params": {
      "object_codes": ["Event"],
      "filters": [
        {"type": "degree", "params": {"metric": "out_minus_in", "op": "gte", "value": 0}}
      ],
      "sort": {
        "by": "similarity",
        "params": {"query": "退货单"}
      },
      "page": 1,
      "pageSize": 20
    }
  }'
```

---

## 条件/排序框架扩展

新增条件类型（如按 `ext_attrs` 属性过滤）或排序依据（如按数值字段排序）的接入成本：

- knowledge 层注册表（`_FILTER_REGISTRY` / `_SORT_REGISTRY`）+1 条目（`validate` ~8 行 + `build` ~15 行，生成 WHERE/HAVING/ORDER BY SQL 片段）
- RPC handler / 接口形状 / 返回模型 **零改动**（filters 数组 / sort 规格透传）
- 非法 `type` / `params` / `by` 由注册表校验抛 ValueError → 自动映射 400

当前注册表：

- filters：`degree`（HAVING 阶段，required_joins: out/in，隐式排序）
- sort：`similarity`（name 级特征，requires_name_join: true，Embedding 向量或 BM25 降级）

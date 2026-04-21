# AGENTS.md

**Module:** intent
**Purpose:** 意图识别 — 消歧、召回、澄清、评分、范式构建

---

## Overview

意图理解原子能力：术语召回→消歧→多轮澄清→评分更新→范式构建。16 个文件，最复杂的子模块。

## Structure

```
intent/
├── service.py             # 对外服务层（with_session 系列函数）
├── types.py               # 公共类型（MatchResult, ClarificationResult 等）
├── batch_recall.py        # 批量术语召回（840L）
├── typed_recall.py        # 按类型分区召回
├── matching.py            # 术语匹配（BM25 + 子串 + 向量）
├── disambiguation.py      # 三层消歧 + 最短路径树（598L）
├── paradigm_builder.py    # 范式解析状态机 ParadigmResolutionState（619L）
├── natquery.py            # NatQuery 结构化查询模型
├── llm_confirm.py         # LLM 确认（ConfirmedQuery 等）
├── score_update.py        # 术语评分更新
├── cache.py               # UserNameCache
├── storage.py             # 术语/知识写入
├── dimension_values.py    # 维度值查询
├── llm_utils.py           # LLM 工具函数
├── clarification_legacy.py # 旧版澄清入口（兼容 shim）
└── clarification/         # 多轮澄清子模块
    ├── api.py             # 澄清 API 入口（411L）
    ├── extract.py         # 意图提取
    ├── confirm.py         # 确认逻辑
    ├── cartesian.py       # 笛卡尔积展开（590L）
    ├── format.py          # 格式化
    └── models.py          # 澄清数据模型
```

## Where to Look

| Task | Location |
|------|----------|
| 对外服务入口 | `service.py:*_with_session()` |
| 术语召回 | `batch_recall.py`, `typed_recall.py` |
| 消歧 | `disambiguation.py:disambiguate()` |
| 最短路径树 | `disambiguation.py:build_shortest_path_tree()` |
| 多轮澄清 | `clarification/api.py` |
| 范式构建 | `paradigm_builder.py:build_paradigm_resolution_state()` |
| 评分更新 | `score_update.py:update_score()` |
| 公共类型 | `types.py` |

## External Consumers

| 符号 | 消费方 |
|------|--------|
| `search_all_candidates_with_name_id` | datacloud-analysis, byclaw-data |
| `disambiguate_with_session` | datacloud-analysis |
| `typed_multi_recall_with_session` | byclaw-data |
| `analyze_query_clarification` | byclaw-data |
| `store_clarification_results` | datacloud-analysis |
| `ScoreUpdateRecord`, `batch_update_scores_with_session` | datacloud-analysis |

## Conventions

- **SQL 裸表名**: 所有 SQL 不硬编码 schema，依赖 SQLAlchemy engine `connect_args` 设置 `search_path`
- **`__init__.py` 导出 58 个符号**: 保持向后兼容，新代码建议直接从子模块导入
- **DEBUG 模式**: `DATACLOUD_INTENT_DEBUG=1` 开启全模块 DEBUG 日志

## Notes

- `batch_recall.py` 840 行 — 最大的 intent 文件
- `clarification/` 是独立子模块，有自己的 models.py
- TODO(ontology): `clarification/api.py` 有待实现的 ontology_code 过滤

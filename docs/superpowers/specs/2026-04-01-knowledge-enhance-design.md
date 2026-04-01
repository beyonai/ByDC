# 知识增强 Pipeline 设计（2026-04-01）

## 1. 背景
- 现有 `knowledge_enhance_node` 只把用户问题直接喂给 `search_knowledge`，无法得到 LLM 提炼后的术语集合，也无法返回 confirmed / ambiguous 等结构化信息。
- 《模块设计/知识增强》文档明确要求一次补齐 5.1~5.5 功能：术语抽取、候选检索、歧义处理、知识加载、产物生成。
- 老节点输出 `term_hints/enriched_query/knowledge_snippets/knowledge_preview`，其中 preview 已无下游消费者，需要移除。

## 2. 设计目标
1. 将知识增强流程改造成固定 5 步的 pipeline，单次调用即可拿到所有结构化结果。
2. AgentState 新增 `concept_terms/confirmed_terms/ambiguous_terms/knowledge_payload` 并重构 `term_hints/enriched_query/knowledge_snippets` 的生成方式。
3. 任一步失败都能降级回旧 `search_knowledge` 流程，避免中断主图且不写入半成品。
4. 新逻辑默认走 pipeline，fallback 只在异常时触发；日志要能覆盖每一步关键指标，便于排查。

## 3. 架构方案
- 在 `knowledge_enhance/node.py` 新增 `KnowledgeEnhancePipeline` 类，暴露 `async run(context) -> PipelineOutput`。
- LangGraph 节点入口逻辑：
  1. 整理 `user_query`、LLM 句柄、工具依赖到 `PipelineContext`。
  2. 调用 `pipeline.run()` 获取 `PipelineOutput`。
  3. 按输出写入 AgentState；若收到 fallback 标记则写入旧结构并记录 warning。
- `PipelineState` + `PipelineOutput`：
  - `PipelineState` 在执行中累计术语列表、候选 map、confirmed/ambiguous、知识 payload 等。
  - `PipelineOutput` 负责提供最终产物（`confirmed_terms`、`ambiguous_terms`、`enriched_query`、`term_hints`、`knowledge_payload`、`knowledge_snippets`、`mode=fresh/fallback`）。

### 3.1 Pipeline 数据结构
```python
@dataclass
class PipelineContext:
    user_query: str
    llm: AsyncLLM
    knowledge_client: KnowledgeService
    logger: logging.Logger

@dataclass
class PipelineState:
    concept_terms: list[str] = field(default_factory=list)
    candidates_map: dict[str, list[CandidateDict]] = field(default_factory=dict)
    confirmed_terms: list[ConfirmedTermDict] = field(default_factory=list)
    ambiguous_terms: list[AmbiguousTermDict] = field(default_factory=list)
    knowledge_payload: dict[str, Any] = field(default_factory=lambda: {"terms": []})
    term_hints: list[dict[str, Any]] = field(default_factory=list)
    enriched_query: str | None = None
    knowledge_snippets: list[str] = field(default_factory=list)
    knowledge_mode: Literal["fresh", "fallback"] = "fresh"

@dataclass
class PipelineOutput:
    state: PipelineState
    mode: Literal["fresh", "fallback"]
```
LangGraph 节点仅负责把 `state` 写回 AgentState，并同步 `knowledge_mode`。

## 4. 步骤拆解
1. **LLM 抽术语** `_extract_concept_terms`
   - 输入：`user_query` + LLM。
   - Prompt 要求输出 JSON list（仅含业务术语、复合名词），解析失败直接抛异常交给 fallback。
2. **候选检索** `_search_candidates_for_terms`
   - 输入：术语列表，去重后截取前 `MAX_TERMS=5` 个。
   - 依次调用 `search_all_candidates(term, top_k=5)`，聚合为 `dict[mention, list[CandidateDict]]`。
3. **歧义处理** `_disambiguate_candidates`
   - 输入：候选 map + 原始问题。
   - 复用 `datacloud_knowledge.intent.matching.disambiguate_candidates`，得到 `confirmed_terms + ambiguous_terms`。
4. **知识加载** `_load_knowledge_for_confirmed`
   - 输入：`confirmed_terms`。
   - 通过 `knowledge_service.load_term_knowledge(term_id)` 拉取详情并合并为单个 `knowledge_payload`（包含指标/维度/样例等）。
5. **产物生成** `_build_outputs`
   - 根据 confirmed 结果构造 `enriched_query`（把术语标准名替换/注释进用户问题）、`term_hints`（兼容旧格式）、`knowledge_snippets`（从 payload 选片段）。

### 4.1 候选结构
```python
CandidateDict = TypedDict(
    "CandidateDict",
    {
        "term_id": str,
        "term_name": str,
        "term_type_code": str,
        "match_type": Literal["standard_name", "alias", "bm25", "vector"],
        "confidence": float,
        "score": float | None,
        "name_id": str | None,
        "mention": str,
    },
)
```
- `_search_candidates_for_terms` 去重 `concept_terms` 后最多保留 5 条。
- 每个术语调用 `search_all_candidates(term, top_k=5)`，写入 `candidates_map[mention]`。
- `disambiguate_candidates` 直接消费 `dict[str, list[CandidateDict]]`，并将优胜者转换为 `ConfirmedTermDict`。

### 4.2 Disambiguate 约定
`disambiguate_candidates` 返回 `(confirmed_terms, ambiguous_terms)`，其中 confirmed 与 §5.1 `ConfirmedTermDict` 对齐；ambiguous 包含 `mention + candidates`。

### 4.3 KnowledgeService 接口
```python
class KnowledgeService(Protocol):
    async def load_term_knowledge(
        self,
        term_id: str,
        *,
        timeout: float = 5.0,
    ) -> KnowledgeTermPayload: ...
```
`KnowledgeTermPayload` 结构在 §5.1 中定义。
- 成功：返回单个 term payload。
- 失败：抛出 `KnowledgeLoadError(term_id=..., reason=...)`；由 `_load_knowledge_for_confirmed` 捕获并记录 warning。
- 超时：抛 `asyncio.TimeoutError`，被视为失败。
- `_load_knowledge_for_confirmed` 并发加载 term，成功的加入 `knowledge_payload["terms"]`；失败项忽略。
- 若 **全部 term 加载失败**，抛 `KnowledgePayloadEmptyError` 触发 fallback。

### 4.4 Confidence 归一化
- `CandidateDict.confidence` 来自底层搜索：
  - `standard_name/alias` 固定为 1.0。
  - `bm25` 根据 `score` 做 `min(score, 1.0)`；若 score 缺失则回退 0.6。
  - `vector` 默认 0.7，若接口提供相似度则 `round(float(sim), 4)` 并截断到 [0,1]。
- `term_hints.confidence`：
  - 确认项直接取 `ConfirmedTermDict.confidence`。
  - ambiguous 候选沿用其候选 confidence。
  - fallback（legacy）固定 1.0。

### 4.5 `_build_outputs` 细化
1. **enriched_query**
   - 先按提及词长度从大到小排序（Longest-first），再按原文本的起始位置从左到右处理，确保复合词优先。
   - 已替换的文本段不会再次替换，避免重复注释。
   - 若 `mention` 与原文一致，则在后方追加 `(<term_name>)` 注释；若标准名不同则直接替换为标准名。
   - 示例：`请查企业综合分析表和企业分析` → `请查企业综合分析表(企业综合分析表)和企业分析(企业综合分析表)`（第二个 mention 复用了同一个 term，允许重复注释）。
2. **term_hints**
   - 顺序：`confirmed_terms` 原序，其次 `ambiguous_terms` 的候选，按 `confidence` 降序。
   - 字段：按照 schema 写入；`source` 取 `confirmed`、`ambiguous`、`fallback` 三种之一。
3. **knowledge_snippets**
   - 来源：遍历 `knowledge_payload.terms`，按 `definition -> metrics -> dimensions -> sample_sql` 优先级拼文本。
   - 限制：最大 5 条、每条 <= 200 字符，超长截断并追加 `...`。

## 5. AgentState 写入
- 正常模式：
  - `concept_terms`: list[str]
  - `confirmed_terms`: list[ConfirmedTermDict]
  - `ambiguous_terms`: list[AmbiguousTermDict]
  - `enriched_query`: str
  - `knowledge_payload`: dict[str, Any]
  - `term_hints`: list[dict[str, Any]]（兼容旧格式）
  - `knowledge_snippets`: list[str]
  - 删除 `knowledge_preview`（不再写入）。
- fallback 模式：`term_hints/enriched_query/knowledge_snippets` 来自旧接口，其余字段写入空结构（参见 §6.1 表格）。

### 5.1 字段 Schema
| 字段 | 类型 | 必填 | 结构定义 | 说明 |
| --- | --- | --- | --- | --- |
| `concept_terms` | list[str] | 是 | 纯字符串数组 | LLM 输出的原始术语，保持用户表达顺序 |
| `ConfirmedTermDict` | TypedDict | 是 | `{ "mention": str, "term_id": str, "term_name": str, "term_type_code": str, "confidence": float, "match_type": Literal["standard_name","alias","bm25","vector"], "name_id": str \| None }` | 结合 disambiguate 输出与候选信息 |
| `AmbiguousTermDict` | TypedDict | 是 | `{ "mention": str, "candidates": list[ConfirmedTermDict] }` | `candidates` 仍沿用 ConfirmedTermDict schema |
| `knowledge_payload` | dict | 是 | `{ "terms": list[ { "term_id": str, "term_name": str, "term_type_code": str, "definition": str \| None, "metrics": list[str], "dimensions": list[str], "sample_sql": str \| None, "sample_result": list[dict] \| None } ] }` | 若需扩展指标/权限类字段，在 `terms[*]` 中追加 |
| `term_hints` | list[dict] | 是 | `{ "term": str, "term_id": str, "term_type": str, "confidence": float, "source": Literal["confirmed","ambiguous","fallback"], "mention": str }` | 兼容旧字段（term/term_id/term_type），新增 source/mention |
| `knowledge_snippets` | list[str] | 否 | 至多 5 条字符串，每条 <= 200 chars | 从 payload 中提炼的简短提示 |
| `knowledge_mode` | Literal["fresh","fallback"] | 否 | 默认为 `fresh` | Fallback 时写 `"fallback"` 方便追溯 |

**示例（happy path）**
```json
{
  "concept_terms": ["企业综合分析表", "效益最低网格"],
  "confirmed_terms": [
    {
      "mention": "企业综合分析表",
      "term_id": "t_enterprise_analysis",
      "term_name": "企业综合分析表",
      "term_type_code": "VIEW",
      "confidence": 0.98,
      "match_type": "standard_name",
      "name_id": "n123"
    }
  ],
  "ambiguous_terms": [],
  "knowledge_payload": {
    "terms": [
      {
        "term_id": "t_enterprise_analysis",
        "term_name": "企业综合分析表",
        "term_type_code": "VIEW",
        "definition": "企业画像综合分析视图。",
        "metrics": ["GMV", "利润率"],
        "dimensions": ["网格", "行业"],
        "sample_sql": "select ...",
        "sample_result": [{"grid_name": "A区", "gmv": 100}]
      }
    ]
  }
}
```

### 5.2 `_build_outputs` 例外场景
- 若 `confirmed_terms` 为空，则 `enriched_query=user_query`，`term_hints` 仅包含 ambiguous/fallback 来源。
- 若同一标准术语在问题里出现多次，按照左到右依次注释。

## 6. Fallback 策略
- **触发条件**：任一步抛出异常或返回非法结构（例如术语解析失败、知识加载全失败）即触发 fallback。
- **流程**：
  1. 捕获异常并 `logger.warning("knowledge_enhance_fallback", step=..., error_message=...)`。
  2. 调 `_fallback_search_knowledge(user_query)`（仅调用旧 `search_knowledge`，不再进入 pipeline）。
  3. fallback 输出写入：`concept_terms=[]`、`confirmed_terms=[]`、`ambiguous_terms=[]`、`knowledge_payload={"terms": []}`、`term_hints/enriched_query/knowledge_snippets` 来自旧接口、`knowledge_mode="fallback"`。
  4. 旧接口字段映射：legacy `term_matches` 每项 `{ "term_name", "term_id", "term_type" }` → `term_hints` 的 `{ term=term_name, term_id, term_type, confidence=1.0, source="fallback", mention=term_name }`；`knowledge_snippets` 直接沿用字符串列表；`enriched_query` 取 legacy 字段。
- **部分失败约定**：
  - LLM 成功但知识加载全部失败 → fallback。
  - 某个 term 加载失败但其余成功 → 仅跳过失败项，记录 warning，不触发 fallback。
  - 候选检索成功但全进 ambiguous → 仍视为 fresh，只是 `confirmed_terms=[]`。
  - 合法空结果：`concept_terms=[]`（例如用户没有术语）但是流程无异常时，视为 fresh，保持 `knowledge_mode="fresh"`。
- **触发阈值说明**（任何一项满足则 fallback）：
  1. LLM 输出非 JSON 或 JSON 解析失败。
  2. 候选检索整体抛异常，或在 `MAX_TERMS=5` 的窗口内所有术语均检索失败。
  3. `confirmed_terms` 非空但知识加载全部失败。
  4. `_build_outputs` 抛异常或返回空字符串。
  5. 任意步骤显式抛出了 `PipelineFatalError`。
- **数据清理**：fallback 时重置 `concept_terms/confirmed_terms/ambiguous_terms/knowledge_payload/knowledge_snippets` 等 pipeline 字段，只保留 legacy `term_hints/enriched_query/knowledge_snippets` 与 `knowledge_mode="fallback"`，避免混入半成品。

### 6.1 Fallback 状态矩阵
| 字段 | fresh | fallback |
| --- | --- | --- |
| `concept_terms` | LLM 输出 | `[]` |
| `confirmed_terms` | disambiguate 结果 | `[]` |
| `ambiguous_terms` | disambiguate 结果 | `[]` |
| `knowledge_payload` | 加载成功项 | `{ "terms": [] }` |
| `term_hints` | confirmed + ambiguous | legacy `term_matches` 适配 |
| `knowledge_snippets` | payload 生成 | legacy snippets |
| `enriched_query` | 注释后的 query | legacy `enriched_query` 或原 query |
| `knowledge_mode` | `"fresh"` | `"fallback"` |

## 7. 日志
统一采用结构化日志，字段见下表。示例：
```python
logger.debug(
    "term_extraction",
    concept_term_count=len(concept_terms),
    sample_terms=concept_terms[:2],
)
```

| 日志点 | level | message | 必填字段 |
| --- | --- | --- | --- |
| 流程开始 | info | `"knowledge_enhance_start"` | `user_query_hash` |
| 术语抽取 | debug | `"term_extraction"` | `concept_term_count`, `sample_terms` |
| 候选检索 | debug | `"candidate_search"` | `mention`, `candidate_count`, `match_types` |
| 歧义处理 | debug | `"term_disambiguation"` | `confirmed_count`, `ambiguous_count` |
| 知识加载 | debug | `"knowledge_load"` | `term_id`, `status` (`"success"/"failed"`), `error`(optional) |
| 产物生成 | debug | `"knowledge_outputs"` | `term_hints_count`, `knowledge_snippets_count` |
| 流程结束 | info | `"knowledge_enhance_end"` | `mode`, `duration_ms` |
| fallback | warning | `"knowledge_enhance_fallback"` | `step`, `error_message` |

## 8. 测试
- `tests/dca/unit/test_knowledge_enhance_pipeline.py`
  1. `test_pipeline_happy_path`：验证 schema、`knowledge_mode="fresh"`、snippet 限制。
  2. `test_pipeline_all_ambiguous`：候选存在但全部进入 ambiguous，确保 `confirmed_terms=[]` 且 query 未追加注释。
  3. `test_pipeline_candidate_search_failure_triggers_fallback`：`search_all_candidates` 抛异常 → fallback 默认值。
  4. `test_pipeline_partial_term_load_failure_skips_term`：某 term 加载失败，其他 term 仍输出，日志包含 warning。
  5. `test_pipeline_fallback_on_llm_error`：LLM 抛异常 → fallback，并断言 `knowledge_mode="fallback"`。
  6. `test_pipeline_removes_knowledge_preview`：确认 AgentState 不再包含旧字段。
  7. `test_pipeline_empty_terms_still_fresh`：LLM 返回空数组但未抛错，验证流程不 fallback、`enriched_query` 原样返回、`knowledge_mode="fresh"`。
  8. `test_pipeline_clears_state_on_fallback`：知识加载阶段抛异常，断言 AgentState 仅含 legacy 字段与 `knowledge_mode="fallback"`。
  9. `test_pipeline_logs_fresh_path`：使用 `caplog` 断言 fresh 流程包含 `term_extraction`、`candidate_search`、`knowledge_enhance_end` 日志及字段。
  10. `test_pipeline_logs_fallback_path`：模拟异常触发 fallback，断言 `knowledge_enhance_fallback` warning 及字段。
- `tests/dca/unit/test_knowledge_enhance_node.py`（若存在）：补集成测试，验证节点对 AgentState/Fallback 标志的写入。
- Mock 依赖：LLM wrapper（固定 JSON）、`search_all_candidates`、`disambiguate_candidates`、`knowledge_service.load_term_knowledge`。必要时参数化 fresh/fallback 场景。

## 9. 风险 & TODO
- `knowledge_service` 可能不存在统一入口，需要先在 `datacloud-knowledge` 导出辅助函数。
- AgentState schema 若在别处定义（pydantic/dataclass），需要同步更新类型注解，并在文档中保持一致。
- 后续可把 pipeline 抽象提炼为基础类，供其他节点（如意图澄清）复用。

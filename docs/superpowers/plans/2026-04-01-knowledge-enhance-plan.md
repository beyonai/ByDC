# Knowledge Enhance Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Replace the legacy knowledge_enhance_node with the five-step pipeline defined in the 最新方案, including state schema changes, structured logging, and comprehensive tests.

**Architecture:** Introduce a dedicated KnowledgeEnhancePipeline (dataclasses + async steps) inside the orchestration package. The LangGraph node becomes a thin wrapper that forwards context, receives PipelineOutput, and writes AgentState fields (including fallback handling). Tool helpers provide candidate search, disambiguation, and knowledge loading abstractions that align with datacloud-knowledge services. Tests cover fresh paths, fallback behavior, and logging contracts.

**Tech Stack:** Python 3.12+, LangGraph, datacloud-knowledge SDK, pytest, ruff, mypy.

---

## Chunk 1: Implementation Plan

-### File Structure Changes
- Update packages/datacloud-analysis/src/datacloud_analysis/orchestration/knowledge_enhance/node.py: host the new `KnowledgeEnhancePipeline` class (as required in the spec), provide helpers, orchestrate fallback, and keep the LangGraph node wrapper in the same file.
- Update packages/datacloud-analysis/src/datacloud_analysis/orchestration/state.py: add `concept_terms`, `confirmed_terms`, `ambiguous_terms`, `knowledge_payload`, `knowledge_mode`, ensure `term_hints/knowledge_snippets` schema matches spec, remove `knowledge_preview`.
- Update packages/datacloud-analysis/src/datacloud_analysis/tools/knowledge.py: expose `CandidateDict` TypedDict, wrap `search_all_candidates` & `disambiguate_candidates`, add `KnowledgeService` protocol + loader helper.
- Update / create tests:
  - New packages/datacloud-analysis/tests/dca/unit/test_knowledge_enhance_pipeline.py covering ten cases per spec.
  - Update packages/datacloud-analysis/tests/dca/unit/test_knowledge_enhance_node.py to reflect new outputs (no knowledge_preview, new fields).
- Optional helper modules (if needed) for fixtures/mocks under tests/dca/unit/conftest.py.

---

### Task 1: Update Tool Layer & Shared Types

**Files:**
- Modify: packages/datacloud-analysis/src/datacloud_analysis/tools/knowledge.py

- [ ] **Step 1:** Implement `CandidateDict`, `ConfirmedTermDict`, `AmbiguousTermDict`, `KnowledgeTermPayload`, `KnowledgeService` protocol, `KnowledgeLoadError`, `_knowledge_client()` helper inside `tools/knowledge.py`. Ensure `search_all_candidates` / `disambiguate_candidates` return typed structures and normalize confidence/score as per spec (standard_name=1.0, bm25 capped, vector defaults, etc.).
- [ ] **Step 2:** Expose a helper for legacy fallback (`search_knowledge`) that the pipeline can reuse without duplicating tool logic.

### Task 2: Implement Pipeline & Integrate Node

**Files:**
- Modify: packages/datacloud-analysis/src/datacloud_analysis/orchestration/knowledge_enhance/node.py
- Modify: packages/datacloud-analysis/src/datacloud_analysis/orchestration/state.py

- [ ] **Step 1:** Update `AgentState` annotations: remove `knowledge_preview`, add explicit fields for `concept_terms`, `confirmed_terms`, `ambiguous_terms`, `knowledge_payload`, `knowledge_mode`, and document schema assumptions for `term_hints/knowledge_snippets`.
- [ ] **Step 2:** In `knowledge_enhance/node.py`, define `PipelineContext`, `PipelineState`, `PipelineOutput`, constants (MAX_TERMS, thresholds), exceptions (`PipelineFatalError`, `KnowledgePayloadEmptyError`), and helper functions per spec. Keep all pipeline code in this module to match the design document.
- [ ] **Step 3:** Implement structured logging helpers emitting the messages/fields from §7 (e.g., `logger.info("knowledge_enhance_start", user_query_hash=...)`).
- [ ] **Step 4:** Ensure `_build_outputs` handles overlapping mentions deterministically (longest-first, left-to-right) and caps snippets at five entries of <= 200 chars, plus fallback adapter that maps legacy payload to new schema, zeroing pipeline fields.
- [ ] **Step 5:** Refactor `knowledge_enhance_node` to assemble `PipelineContext` (user query, LLM handle, knowledge client, logger). Call `KnowledgeEnhancePipeline.run()`, map its state onto AgentState, delete legacy helper functions, and ensure fallback path sets `knowledge_mode` + empty field values per §6.1 matrix. Respect `term_hint_confidence_threshold` config.

### Task 3: Update Tests for New Architecture

**Files:**
- Create: packages/datacloud-analysis/tests/dca/unit/test_knowledge_enhance_pipeline.py
- Modify: packages/datacloud-analysis/tests/dca/unit/test_knowledge_enhance_node.py
- Modify: packages/datacloud-analysis/tests/dca/unit/conftest.py (if shared fixtures needed)

- [ ] **Step 1:** Build pytest fixtures for fake LLM, fake knowledge client/service, and instrumented logger (capturing structured records). Provide utilities to stub search_all_candidates, disambiguate_candidates, and load_term_knowledge per test case.
- [ ] **Step 2:** Author the ten pipeline tests listed in spec §8, asserting schema contents, fallback clearing, logging presence, etc. Use `caplog` to verify log messages + fields.
- [ ] **Step 3:** Update `test_knowledge_enhance_node.py` to reflect new node output: remove checks for `knowledge_preview`, assert `knowledge_mode`, confirm AgentState receives pipeline fields, and ensure fallback/respect-threshold scenarios adapt to new architecture.

### Task 4: QA & Documentation

**Files:**
- Modify: docs/superpowers/specs/2026-04-01-knowledge-enhance-design.md (if deviations)
- Modify: docs/superpowers/plans/2026-04-01-knowledge-enhance-plan.md (this file, after execution to check off steps)

- [ ] **Step 1:** Run uv run ruff format packages/datacloud-analysis/src/datacloud_analysis/orchestration/knowledge_enhance and project tests: uv run pytest packages/datacloud-analysis/tests/dca/unit -k knowledge_enhance -v.
- [ ] **Step 2:** Verify mypy (if enabled) passes for modified packages: uv run mypy packages/datacloud-analysis/src/datacloud_analysis/orchestration/knowledge_enhance.
- [ ] **Step 3:** Update documentation/CHANGELOG if necessary (note removal of knowledge_preview, addition of knowledge_mode).
- [ ] **Step 4:** Ensure plan checkboxes are updated before implementation PR/branch merge.

---

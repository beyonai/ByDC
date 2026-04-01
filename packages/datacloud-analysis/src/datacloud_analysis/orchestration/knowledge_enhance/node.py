"""Knowledge enhancement node for the 5-node main pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Sequence

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from datacloud_analysis.orchestration.shared import (
    resolve_reasoning_api_key,
    resolve_reasoning_base_url,
    resolve_reasoning_model_spec,
)
from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tools.knowledge import (
    CandidateDict,
    disambiguate_candidates,
    search_all_candidates,
    search_knowledge,
)
from datacloud_knowledge.query import get_singleton_service

logger = logging.getLogger(__name__)
_MAX_TERMS = 5
_MAX_SNIPPETS = 5
_MAX_SNIPPET_LENGTH = 200
_REWRITE_CONFIDENCE_THRESHOLD = 0.8
_DEFAULT_MODEL = os.getenv("DATACLOUD_LLM_REASONING_MODEL", "Qwen/Qwen3-235B-A22B")


class PipelineFatalError(RuntimeError):
    """Raised when any pipeline step reports an unrecoverable error."""


@dataclass
class PipelineContext:
    """Runtime dependencies used by the pipeline."""

    user_query: str
    llm: Any | None


@dataclass
class PipelineState:
    """Mutable pipeline state captured after each step."""

    user_query: str
    concept_terms: list[str] = field(default_factory=list)
    confirmed_terms: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_terms: list[dict[str, Any]] = field(default_factory=list)
    knowledge_payload: dict[str, Any] = field(default_factory=lambda: {"terms": []})
    term_hints: list[dict[str, Any]] = field(default_factory=list)
    knowledge_snippets: list[dict[str, Any]] = field(default_factory=list)
    enriched_query: str = ""
    enriched_query_source: str = "user_query"
    enriched_query_confidence: float = 0.0

    def to_agent_updates(self, *, mode: str) -> dict[str, Any]:
        """Format a dict compatible with AgentState updates."""
        return {
            "user_query": self.user_query,
            "concept_terms": list(self.concept_terms),
            "confirmed_terms": list(self.confirmed_terms),
            "ambiguous_terms": list(self.ambiguous_terms),
            "knowledge_payload": dict(self.knowledge_payload),
            "term_hints": list(self.term_hints),
            "knowledge_snippets": list(self.knowledge_snippets),
            "knowledge_mode": mode,
            "enriched_query": self.enriched_query or self.user_query,
            "enriched_query_source": self.enriched_query_source,
            "enriched_query_confidence": self.enriched_query_confidence,
        }


@dataclass
class PipelineOutput:
    """Final pipeline result returned to the LangGraph node."""

    state: PipelineState
    mode: str


class KnowledgeEnhancePipeline:
    """LLM-backed pipeline that extracts + enriches structured knowledge."""

    def __init__(
        self,
        context: PipelineContext,
        *,
        logger: logging.Logger,
    ) -> None:
        self._ctx = context
        self._logger = logger

    async def run(self) -> PipelineOutput:
        state = PipelineState(user_query=self._ctx.user_query)
        try:
            state.concept_terms = await self._extract_concept_terms(self._ctx.user_query)
            candidates = await self._search_candidates(state.concept_terms)
            confirmed, ambiguous = await self._disambiguate(candidates)
            state.confirmed_terms = confirmed
            state.ambiguous_terms = ambiguous
            state.knowledge_payload = await self._load_knowledge(confirmed)
            (
                state.enriched_query,
                state.enriched_query_source,
                state.enriched_query_confidence,
            ) = self._rewrite_query(self._ctx.user_query, confirmed)
            state.term_hints = self._build_term_hints(confirmed, ambiguous)
            state.knowledge_snippets = self._build_snippets(state.knowledge_payload)
            return PipelineOutput(state=state, mode="fresh")
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("knowledge_enhance pipeline failed, fallback to legacy search: %s", exc)
            return await self._fallback(state)

    async def _extract_concept_terms(self, user_query: str) -> list[str]:
        if not user_query.strip():
            return []
        llm = self._ctx.llm
        if llm is None:
            # Without an LLM fall back to a naive heuristic: keep quoted substrings.
            return self._extract_terms_by_heuristics(user_query)

        system_prompt = (
            "你是术语抽取助手。"
            "请阅读用户的问题，从中识别需要进知识库查找的业务术语，并以 JSON 字符串数组输出。"
            "只允许返回字符串数组，不要解释。"
        )
        user_prompt = f"用户问题：{user_query}\n\n请返回 JSON 数组，例如 [\"企业综合分析表\", \"网格\"]。"
        response = await llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        content = str(response.content).strip()
        try:
            if "```json" in content:
                content = content.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in content:
                content = content.split("```", 1)[1].split("```", 1)[0]
            candidates = json.loads(content)
        except Exception as exc:  # noqa: BLE001
            raise PipelineFatalError("concept_term_parsing_failed") from exc

        if not isinstance(candidates, Sequence):
            raise PipelineFatalError("concept_term_invalid_shape")

        terms: list[str] = []
        for item in candidates:
            if isinstance(item, str) and item.strip():
                terms.append(item.strip())
        if not terms:
            return self._extract_terms_by_heuristics(user_query)
        return terms[:_MAX_TERMS]

    def _extract_terms_by_heuristics(self, user_query: str) -> list[str]:
        """Fallback tokenizer when LLM is unavailable."""
        raw_terms: list[str] = []
        buffer = ""
        capturing = False
        for ch in user_query:
            if ch in {"“", "\"", "「", "【", "["}:
                capturing = True
                buffer = ""
                continue
            if ch in {"”", "\"", "」", "】", "]"}:
                capturing = False
                if buffer.strip():
                    raw_terms.append(buffer.strip())
                buffer = ""
                continue
            if capturing:
                buffer += ch
        if buffer.strip():
            raw_terms.append(buffer.strip())
        return raw_terms[:_MAX_TERMS]

    async def _search_candidates(self, concept_terms: list[str]) -> dict[str, list[CandidateDict]]:
        if not concept_terms:
            return {}
        candidates: dict[str, list[CandidateDict]] = await search_all_candidates(
            concept_terms[:_MAX_TERMS],
            top_k=5,
        )
        return candidates

    async def _disambiguate(
        self,
        candidates: dict[str, list[CandidateDict]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not candidates:
            return [], []
        llm = self._ctx.llm
        if llm is None:
            confirmed: list[dict[str, Any]] = []
            ambiguous: list[dict[str, Any]] = []
            for mention, options in candidates.items():
                if not options:
                    continue
                primary = options[0]
                confirmed.append(
                    {
                        "mention": mention,
                        "term_id": primary.get("term_id", ""),
                        "term_name": primary.get("term_name", ""),
                        "term_type_code": primary.get("term_type_code", ""),
                        "confidence": float(primary.get("confidence", 0.0) or 0.0),
                    }
                )
                if len(options) > 1:
                    ambiguous.append({"mention": mention, "candidates": options[1:]})
            return confirmed, ambiguous
        confirmed, ambiguous = await disambiguate_candidates(
            candidates,
            original_question=self._ctx.user_query,
            llm=llm,
        )
        return confirmed, ambiguous

    async def _load_knowledge(self, confirmed_terms: list[dict[str, Any]]) -> dict[str, Any]:
        if not confirmed_terms:
            return {"terms": []}

        def _run_query() -> list[dict[str, Any]]:
            try:
                service = get_singleton_service(n_hops=1, fast=True, warm_pool=False)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("knowledge_enhance: init knowledge service failed: %s", exc)
                return []

            enriched_terms: list[dict[str, Any]] = []
            for term in confirmed_terms:
                term_id = str(term.get("term_id", "")).strip()
                term_name = str(term.get("term_name") or term.get("mention") or "").strip()
                if not term_name:
                    continue
                try:
                    result = service.query(term_name, n_hops=0, include_knowledge=True)
                except Exception as exc:  # noqa: BLE001
                    self._logger.warning(
                        "knowledge_enhance: knowledge query failed term=%s term_id=%s err=%s",
                        term_name,
                        term_id,
                        exc,
                    )
                    definition = None
                else:
                    definition = self._extract_definition_from_result(result, term_id)

                enriched_terms.append(
                    {
                        "term_id": term_id or term_name,
                        "term_name": term_name or term_id,
                        "term_type_code": str(term.get("term_type_code", "")),
                        "definition": definition,
                        "metrics": [],
                        "dimensions": [],
                        "sample_sql": None,
                        "sample_result": None,
                    }
                )
            return enriched_terms

        terms_payload = await asyncio.to_thread(_run_query)
        return {"terms": terms_payload}

    def _extract_definition_from_result(self, result: dict[str, Any], target_term_id: str) -> str | None:
        results = result.get("results") or []
        knowledge_texts: list[str] = []
        for subgraph in results:
            tree = subgraph.get("tree")
            knowledge_texts.extend(self._collect_knowledge_from_tree(tree, target_term_id))
        if not knowledge_texts:
            for subgraph in results:
                center_id = str(subgraph.get("center_entity", {}).get("node_id", ""))
                tree = subgraph.get("tree")
                knowledge_texts.extend(self._collect_knowledge_from_tree(tree, center_id))
        definition = "\n\n".join(dict.fromkeys(text for text in knowledge_texts if text))
        return definition or None

    def _collect_knowledge_from_tree(
        self,
        tree: dict[str, Any] | None,
        target_id: str,
    ) -> list[str]:
        if not tree or not isinstance(tree, dict):
            return []
        texts: list[str] = []
        node_id = str(tree.get("id") or "")
        properties = tree.get("properties") or {}
        knowledge_items = properties.get("knowledge")
        if knowledge_items and (not target_id or node_id == target_id):
            if isinstance(knowledge_items, list):
                texts.extend(str(item) for item in knowledge_items if item)
            else:
                texts.append(str(knowledge_items))
        for child in tree.get("children") or []:
            texts.extend(self._collect_knowledge_from_tree(child, target_id))
        return texts

    def _rewrite_query(
        self,
        user_query: str,
        confirmed_terms: list[dict[str, Any]],
    ) -> tuple[str, str, float]:
        rewritten = user_query
        rewrite_confidence = 0.0
        replaced = False
        ordered = sorted(
            confirmed_terms,
            key=lambda item: len(str(item.get("mention") or item.get("term_name") or "")),
            reverse=True,
        )
        for term in ordered:
            mention = str(term.get("mention") or term.get("term_name") or "").strip()
            normalized = str(term.get("term_name") or mention).strip()
            confidence = float(term.get("confidence", 0.0) or 0.0)
            if (
                not mention
                or not normalized
                or mention == normalized
                or confidence < _REWRITE_CONFIDENCE_THRESHOLD
            ):
                continue
            if mention in rewritten:
                rewritten = rewritten.replace(mention, f"{mention}({normalized})")
                rewrite_confidence = max(rewrite_confidence, confidence)
                replaced = True

        if replaced:
            return rewritten, "knowledge_rewrite", rewrite_confidence
        return user_query, "user_query", 0.0

    def _build_term_hints(
        self,
        confirmed_terms: list[dict[str, Any]],
        ambiguous_terms: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        term_hints: list[dict[str, Any]] = []

        def _semantic_type(term_type_code: str) -> str:
            raw = term_type_code.upper()
            if "ACTION" in raw:
                return "action"
            if "RELATION" in raw:
                return "relation"
            if "VIEW" in raw:
                return "view"
            return "object"

        for item in confirmed_terms:
            term_hints.append(
                {
                    "term": item.get("term_name", ""),
                    "term_id": item.get("term_id", ""),
                    "term_type": item.get("term_type_code", ""),
                    "mention": item.get("mention", item.get("term_name", "")),
                    "normalized_term": item.get("term_name", ""),
                    "confidence": float(item.get("confidence", 0.0) or 0.0),
                    "source": item.get("source", "confirmed"),
                    "semantic_type": _semantic_type(str(item.get("term_type_code", ""))),
                    "note": "",
                }
            )

        for item in ambiguous_terms:
            mention = str(item.get("mention", ""))
            for candidate in item.get("candidates", []):
                term_hints.append(
                    {
                        "term": candidate.get("term_name", ""),
                        "term_id": candidate.get("term_id", ""),
                        "term_type": candidate.get("term_type_code", ""),
                        "mention": mention or candidate.get("term_name", ""),
                        "normalized_term": candidate.get("term_name", ""),
                        "confidence": float(candidate.get("confidence", 0.0) or 0.0),
                        "source": "ambiguous",
                        "semantic_type": _semantic_type(str(candidate.get("term_type_code", ""))),
                        "note": "",
                    }
                )
        return term_hints

    def _build_snippets(self, knowledge_payload: dict[str, Any]) -> list[dict[str, Any]]:
        snippets: list[dict[str, Any]] = []
        terms = knowledge_payload.get("terms", []) if isinstance(knowledge_payload, dict) else []
        for term in terms[:_MAX_SNIPPETS]:
            text = term.get("definition") or term.get("term_name")
            if not text:
                continue
            snippet = str(text)[:_MAX_SNIPPET_LENGTH]
            snippets.append({"source": "confirmed_terms", "data": {"term": term.get("term_name"), "text": snippet}})
        return snippets

    async def _fallback(self, _: PipelineState) -> PipelineOutput:
        payload = {}
        try:
            payload = await search_knowledge.ainvoke({"query": self._ctx.user_query})
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("knowledge_enhance fallback search failed: %s", exc)
        hints = self._legacy_hints(payload)
        snippets = self._legacy_snippets(payload)
        state = PipelineState(
            user_query=self._ctx.user_query,
            knowledge_payload=payload if isinstance(payload, dict) else {"terms": []},
            term_hints=hints,
            knowledge_snippets=snippets,
        )
        return PipelineOutput(state=state, mode="fallback")

    def _legacy_hints(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        hints: list[dict[str, Any]] = []
        matches = payload.get("term_matches", []) if isinstance(payload, dict) else []
        for row in matches:
            hints.append(
                {
                    "term": row.get("term_name", ""),
                    "term_id": row.get("term_id", ""),
                    "term_type": row.get("term_type_code", ""),
                    "mention": row.get("term_name", ""),
                    "normalized_term": row.get("term_name", ""),
                    "confidence": float(row.get("match_score", 0.0) or 0.0),
                    "source": "fallback",
                    "semantic_type": "",
                    "note": "",
                }
            )
        return hints

    def _legacy_snippets(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        snippets: list[dict[str, Any]] = []
        if payload.get("term_matches"):
            snippets.append({"source": "term_matches", "data": payload.get("term_matches")})
        if payload.get("fuzzy_term_matches"):
            snippets.append({"source": "fuzzy_term_matches", "data": payload.get("fuzzy_term_matches")})
        return snippets[:_MAX_SNIPPETS]


def _init_reasoning_llm() -> Any | None:
    try:
        model_spec = resolve_reasoning_model_spec(_DEFAULT_MODEL)
        llm = init_chat_model(
            model=model_spec["model"],
            model_provider=model_spec["model_provider"],
            api_key=resolve_reasoning_api_key(),
            base_url=resolve_reasoning_base_url(),
        )
        return llm
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge_enhance: failed to init reasoning llm: %s", exc)
        return None


def _last_user_text(messages: list[Any]) -> str:
    if not messages:
        return ""
    last = messages[-1]
    content = getattr(last, "content", "")
    if isinstance(content, str):
        return content
    return str(content)


async def knowledge_enhance_node(
    state: AgentState,
    gateway_context: Any = None,
) -> dict[str, Any]:
    """Build structured enhancement artifacts for downstream planning."""
    _ = gateway_context  # reserved for future hooks
    user_query = _last_user_text(list(state.get("messages", [])))
    if not user_query.strip():
        return {
            "user_query": "",
            "enriched_query": "",
            "enriched_query_source": "empty_query",
            "enriched_query_confidence": 0.0,
            "term_hints": [],
            "knowledge_snippets": [],
            "knowledge_payload": {"terms": []},
            "knowledge_mode": "fresh",
            "concept_terms": [],
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    context = PipelineContext(user_query=user_query, llm=_init_reasoning_llm())
    pipeline = KnowledgeEnhancePipeline(context, logger=logger)
    output = await pipeline.run()
    return output.state.to_agent_updates(mode=output.mode)

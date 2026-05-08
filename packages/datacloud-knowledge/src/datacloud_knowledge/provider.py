"""Knowledge provider facade.

This module keeps the public knowledge API thin and delegates to the existing
local function implementation.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from datacloud_knowledge.intent.clarification.api import (
    analyze_query_clarification as _analyze_query_clarification,
)
from datacloud_knowledge.intent.clarification.api import (
    format_clarification_compute as _format_clarification_compute,
)
from datacloud_knowledge.intent.clarification.api import (
    format_clarification_query as _format_clarification_query,
)
from datacloud_knowledge.intent.clarification.postprocess import (
    normalize_clarification_params as _normalize_clarification_params,
)
from datacloud_knowledge.intent.clarification.postprocess import (
    persist_confirmed_synonyms as _persist_confirmed_synonyms,
)
from datacloud_knowledge.knowledge_search import (
    resolve_field_aliases as _resolve_field_aliases,
)
from datacloud_knowledge.knowledge_search import (
    search_terms_by_type as _search_terms_by_type,
)
from datacloud_knowledge.knowledge_search.types import (
    FieldResolutionResult,
    SearchTermsResult,
    TagFilter,
)

logger = logging.getLogger(__name__)

ClarificationMode = Literal["query", "compute"]
OpaquePayload = dict[str, Any] | list[Any] | str

_PROVIDER_MODE_ENV = "DATACLOUD_KNOWLEDGE_PROVIDER_MODE"
_PROVIDER_MODE_FUNCTION = "function"
_PROVIDER_MODE_API = "api"

_provider: KnowledgeProvider | None = None


@dataclass(frozen=True, slots=True)
class PersistedSynonyms:
    """Synonyms persisted during clarification finalization."""

    created_ids: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FinalizedClarification:
    """Finalized clarification output."""

    structured_input: dict[str, Any]
    changed_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    persisted_synonyms: PersistedSynonyms | None = None


@dataclass(frozen=True, slots=True)
class ClarificationAnalysis:
    """Clarification analysis result."""

    needs_clarification: bool
    form: OpaquePayload | None = None
    metadata: OpaquePayload | None = None

    @property
    def knowledge(self) -> OpaquePayload | None:
        """Legacy alias for metadata."""
        return self.metadata


class KnowledgeProvider(Protocol):
    def resolve_field_aliases(
        self,
        *,
        terms: Sequence[str],
        scope_code: str,
        library_id: str | None = None,
        user_id: str | None = None,
        resolve_values: bool = False,
        value_terms: Sequence[str] | None = None,
    ) -> FieldResolutionResult: ...

    def prepare_query_clarification(
        self,
        *,
        query: str,
        ontology_code: str,
        structured_input: Mapping[str, Any],
        mode: ClarificationMode,
    ) -> ClarificationAnalysis: ...

    def finalize_query_clarification(
        self,
        *,
        query: str,
        ontology_code: str,
        structured_input: Mapping[str, Any],
        mode: ClarificationMode,
        needs_clarification: bool,
        form: OpaquePayload | None = None,
        metadata: OpaquePayload | None = None,
        user_id: str | None = None,
        persist_confirmed_synonyms: bool = True,
        idempotency_key: str | None = None,
    ) -> FinalizedClarification: ...

    def search_terms_by_type(
        self,
        *,
        term_type_code: str,
        term_codes: Sequence[str] | None = None,
        keyword: str | None = None,
        tags: Sequence[TagFilter] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "relevance",
    ) -> SearchTermsResult: ...


class FunctionKnowledgeProvider:
    """Knowledge provider backed by in-process functions."""

    def resolve_field_aliases(
        self,
        *,
        terms: Sequence[str],
        scope_code: str,
        library_id: str | None = None,
        user_id: str | None = None,
        resolve_values: bool = False,
        value_terms: Sequence[str] | None = None,
    ) -> FieldResolutionResult:
        return _resolve_field_aliases(
            terms=list(terms),
            scope_code=scope_code,
            library_id=library_id,
            user_id=user_id,
            resolve_values=resolve_values,
            value_terms=list(value_terms) if value_terms is not None else None,
        )

    def prepare_query_clarification(
        self,
        *,
        query: str,
        ontology_code: str,
        structured_input: Mapping[str, Any],
        mode: ClarificationMode,
    ) -> ClarificationAnalysis:
        _validate_mode(mode)
        analysis = _analyze_query_clarification(
            query=query,
            ontology_code=ontology_code,
            structured_input=dict(structured_input),
            mode=mode,
        )
        return ClarificationAnalysis(
            needs_clarification=analysis.needs_clarification,
            form=analysis.form or None,
            metadata=analysis.knowledge or None,
        )

    def finalize_query_clarification(
        self,
        *,
        query: str,
        ontology_code: str,
        structured_input: Mapping[str, Any],
        mode: ClarificationMode,
        needs_clarification: bool,
        form: OpaquePayload | None = None,
        metadata: OpaquePayload | None = None,
        user_id: str | None = None,
        persist_confirmed_synonyms: bool = True,
        idempotency_key: str | None = None,
    ) -> FinalizedClarification:
        del idempotency_key

        _validate_mode(mode)

        original_input = dict(structured_input)
        warnings: list[str] = []
        persisted_synonyms: PersistedSynonyms | None = None

        if needs_clarification:
            if form is None or metadata is None:
                raise ValueError("form and metadata are required when needs_clarification is True")
            form_text = _serialize_payload(form)
            metadata_text = _serialize_payload(metadata)
            formatter = (
                _format_clarification_query if mode == "query" else _format_clarification_compute
            )
            formatted = formatter(query, original_input, form_text, metadata_text)
        else:
            formatted = original_input

        normalized = _normalize_clarification_params(
            formatted,
            ontology_code=ontology_code,
            user_id=user_id,
        )

        if persist_confirmed_synonyms and user_id and needs_clarification:
            try:
                created_ids = _persist_confirmed_synonyms(
                    paradigm_list=_extract_paradigm_list(form),
                    ontology_code=ontology_code,
                    user_id=user_id,
                )
            except Exception as exc:  # pragma: no cover - defensive logging path
                logger.warning("[provider] failed to persist confirmed synonyms: %s", exc)
                warnings.append(f"persist_confirmed_synonyms failed: {exc}")
                created_ids = []
            persisted_synonyms = PersistedSynonyms(created_ids=created_ids)

        changed_paths = _collect_changed_paths(original_input, normalized)
        return FinalizedClarification(
            structured_input=normalized,
            changed_paths=changed_paths,
            warnings=warnings,
            persisted_synonyms=persisted_synonyms,
        )

    def search_terms_by_type(
        self,
        *,
        term_type_code: str,
        term_codes: Sequence[str] | None = None,
        keyword: str | None = None,
        tags: Sequence[TagFilter] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "relevance",
    ) -> SearchTermsResult:
        return _search_terms_by_type(
            term_type_code=term_type_code,
            term_codes=list(term_codes) if term_codes is not None else None,
            keyword=keyword,
            tags=list(tags) if tags is not None else None,
            limit=limit,
            offset=offset,
            order_by=order_by,
        )


def get_provider() -> KnowledgeProvider:
    global _provider
    if _provider is None:
        _provider = _create_provider_from_settings()
    return _provider


def reset_provider(provider: KnowledgeProvider | None = None) -> None:
    global _provider
    _provider = provider


def resolve_field_aliases(
    *,
    terms: Sequence[str],
    scope_code: str,
    library_id: str | None = None,
    user_id: str | None = None,
    resolve_values: bool = False,
    value_terms: Sequence[str] | None = None,
) -> FieldResolutionResult:
    return get_provider().resolve_field_aliases(
        terms=terms,
        scope_code=scope_code,
        library_id=library_id,
        user_id=user_id,
        resolve_values=resolve_values,
        value_terms=value_terms,
    )


def prepare_query_clarification(
    *,
    query: str,
    ontology_code: str,
    structured_input: Mapping[str, Any],
    mode: ClarificationMode,
) -> ClarificationAnalysis:
    return get_provider().prepare_query_clarification(
        query=query,
        ontology_code=ontology_code,
        structured_input=structured_input,
        mode=mode,
    )


def finalize_query_clarification(
    *,
    query: str,
    ontology_code: str,
    structured_input: Mapping[str, Any],
    mode: ClarificationMode,
    needs_clarification: bool,
    form: OpaquePayload | None = None,
    metadata: OpaquePayload | None = None,
    user_id: str | None = None,
    persist_confirmed_synonyms: bool = True,
    idempotency_key: str | None = None,
) -> FinalizedClarification:
    return get_provider().finalize_query_clarification(
        query=query,
        ontology_code=ontology_code,
        structured_input=structured_input,
        mode=mode,
        needs_clarification=needs_clarification,
        form=form,
        metadata=metadata,
        user_id=user_id,
        persist_confirmed_synonyms=persist_confirmed_synonyms,
        idempotency_key=idempotency_key,
    )


def search_terms_by_type(
    *,
    term_type_code: str,
    term_codes: Sequence[str] | None = None,
    keyword: str | None = None,
    tags: Sequence[TagFilter] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = "relevance",
) -> SearchTermsResult:
    return get_provider().search_terms_by_type(
        term_type_code=term_type_code,
        term_codes=term_codes,
        keyword=keyword,
        tags=tags,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )


def _create_provider_from_settings() -> KnowledgeProvider:
    mode = os.getenv(_PROVIDER_MODE_ENV, _PROVIDER_MODE_FUNCTION).strip().lower()
    if mode == _PROVIDER_MODE_FUNCTION:
        return FunctionKnowledgeProvider()
    if mode == _PROVIDER_MODE_API:
        raise NotImplementedError("API knowledge provider is not implemented yet")
    raise ValueError(f"Unsupported knowledge provider mode: {mode}")


def _validate_mode(mode: ClarificationMode) -> None:
    if mode not in ("query", "compute"):
        raise ValueError(f"Unsupported clarification mode: {mode}")


def _serialize_payload(payload: OpaquePayload) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False)


def _extract_paradigm_list(form: OpaquePayload | None) -> list[dict[str, Any]]:
    if form is None:
        return []

    data: Any = form
    if isinstance(form, str):
        try:
            data = json.loads(form) if form else {}
        except (json.JSONDecodeError, ValueError):
            logger.warning("[provider] failed to parse form payload")
            return []

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        paradigm_list = data.get("paradigmList")
        if isinstance(paradigm_list, list):
            return [item for item in paradigm_list if isinstance(item, dict)]
    return []


def _collect_changed_paths(before: Any, after: Any, prefix: str = "") -> list[str]:
    if before == after:
        return []

    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: list[str] = []
        keys = sorted(set(before.keys()) | set(after.keys()), key=str)
        for key in keys:
            key_path = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_collect_changed_paths(before.get(key), after.get(key), key_path))
        return paths or ([prefix] if prefix else [])

    if isinstance(before, list) and isinstance(after, list):
        child_paths: list[str] = []
        max_len = max(len(before), len(after))
        for idx in range(max_len):
            item_path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            before_item = before[idx] if idx < len(before) else None
            after_item = after[idx] if idx < len(after) else None
            child_paths.extend(_collect_changed_paths(before_item, after_item, item_path))
        return child_paths or ([prefix] if prefix else [])

    return [prefix or "$"]


__all__ = [
    "ClarificationAnalysis",
    "ClarificationMode",
    "FinalizedClarification",
    "FunctionKnowledgeProvider",
    "KnowledgeProvider",
    "PersistedSynonyms",
    "finalize_query_clarification",
    "get_provider",
    "prepare_query_clarification",
    "reset_provider",
    "resolve_field_aliases",
    "search_terms_by_type",
]

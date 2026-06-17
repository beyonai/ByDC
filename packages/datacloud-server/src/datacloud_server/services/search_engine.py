"""SearchEngine — multi-scene search for Agent use.

Injects scopes at init time (scope caching), exposes a single-entry
search() method that needs only keyword + query constraints.

Differs from OntologySearchService (single-scene REST API):
  - scopes cached at init — no base_id/scene_id per call
  - internal Adapter reference cache avoids router.get() on every search
  - (base_id, hit_identity) dedup across scenes
  - pluggable SearchStrategy (Direct / RRF / custom)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datacloud_server.ports.ontology_repository import OntologyRepository
    from datacloud_server.services.adapter_router import AdapterRouter


# ── Strategy Protocol ────────────────────────────────────────────

class SearchStrategy(Protocol):
    """Search strategy interface.

    Called by SearchEngine.search() — provides a keyword + pre-cached
    targets list and returns a flat list of hit dicts, each tagged with
    ``_base_id`` for downstream dedup.
    """

    def __call__(
        self,
        keyword: str,
        targets: list[tuple[OntologyRepository, str, str]],
        *,
        search_scope: str = "all",
        result_per_type: int = 5,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...


# ── Internal helpers ─────────────────────────────────────────────

def _flatten_hits(
    result: dict[str, Any],
    base_id: str,
    scene_id: str,
) -> list[dict[str, Any]]:
    """Flatten a search_ontology() dict into tagged hit dicts.

    Each hit gets ``_base_id`` for dedup + ``_scene_id`` for filtering.
    """
    hits: list[dict[str, Any]] = []
    for hit in result.get("metadata", []):
        hit["_base_id"] = base_id
        hit["_scene_id"] = scene_id
        hits.append(hit)
    for hit in result.get("instances", []):
        hit["_base_id"] = base_id
        hit["_scene_id"] = scene_id
        hits.append(hit)
    return hits


def _hit_identity(hit: dict[str, Any]) -> str:
    """Stable identity key for dedup: {base_id}/{resultType}/{code}.

    Metadata hit identity = base_id / resultType / type-specific code.
    Instance hit identity  = base_id / instance / objectCode:primaryKey.
    """
    base_id = hit.get("_base_id", "")
    rt = hit.get("resultType", "")
    if rt == "object":
        return f"{base_id}/object/{hit.get('objectCode', '')}"
    if rt == "view":
        return f"{base_id}/view/{hit.get('viewCode', '')}"
    if rt == "action":
        return f"{base_id}/action/{hit.get('actionCode', '')}"
    if rt in ("prop", "func"):
        return f"{base_id}/{rt}/{hit.get('propertyCode', '')}"
    # Instance hit
    oc = hit.get("objectCode", "")
    pk = hit.get("primaryKey", "")
    return f"{base_id}/instance/{oc}:{pk}"


# ── Built-in strategies ──────────────────────────────────────────

class DirectStrategy:
    """Pass-through — calls search_ontology per target, flattens, no re-rank."""

    def __call__(
        self,
        keyword: str,
        targets: list[tuple[OntologyRepository, str, str]],
        *,
        search_scope: str = "all",
        result_per_type: int = 5,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for adapter, base_id, scene_id in targets:
            raw = adapter.search_ontology(
                base_id, scene_id,
                keyword=keyword,
                search_scope=search_scope,
                result_per_type=result_per_type,
                object_code=object_code,
                view_code=view_code,
            )
            results.extend(_flatten_hits(raw, base_id, scene_id))
        return results


class RRFStrategy:
    """jieba word-level tokenization → per-token search → RRF fusion.

    Splits keyword with jieba, searches each token independently,
    then fuses results via Reciprocal Rank Fusion (RRF).

    Args:
        rrf_k: RRF smoothing constant (default 60, standard BM25-RRF choice).
    """

    def __init__(self, rrf_k: int = 60) -> None:
        self._rrf_k = rrf_k

    def __call__(
        self,
        keyword: str,
        targets: list[tuple[OntologyRepository, str, str]],
        *,
        search_scope: str = "all",
        result_per_type: int = 5,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        import jieba  # noqa: PLC0415  # lazy import — only needed for RRF

        tokens = list(jieba.cut(keyword)) if keyword else []

        # {identity_key: [rank, ...]} — one rank per token match
        scored: dict[str, list[int]] = {}
        docs: dict[str, dict[str, Any]] = {}

        for token in tokens:
            for adapter, base_id, scene_id in targets:
                raw = adapter.search_ontology(
                    base_id, scene_id,
                    keyword=token,
                    search_scope=search_scope,
                    result_per_type=result_per_type,
                    object_code=object_code,
                    view_code=view_code,
                )
                hits = _flatten_hits(raw, base_id, scene_id)
                for rank, hit in enumerate(hits):
                    key = _hit_identity(hit)
                    scored.setdefault(key, []).append(rank)
                    if key not in docs:
                        docs[key] = hit

        return self._rrf_fuse(scored, docs)

    def _rrf_fuse(
        self,
        scored: dict[str, list[int]],
        docs: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Fuse per-token rank lists into a single ranked result via RRF."""
        scores: dict[str, float] = defaultdict(float)
        for key, ranks in scored.items():
            for rank in ranks:
                scores[key] += 1.0 / (self._rrf_k + rank + 1)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [docs[key] for key, _ in ranked if key in docs]


# ── SearchEngine ─────────────────────────────────────────────────

@dataclass
class SearchEngine:
    """Agent multi-scene search engine.

    Scopes are cached at init time — no need to pass base_id/scene_id
    on every search() call.  Internally resolves Adapter references once
    to avoid router.get() overhead on hot path.

    Args:
        router: AdapterRouter for resolving base_id → OntologyRepository.
        scopes: List of (base_id, scene_id) tuples to search across.
        strategy: Default strategy (DirectStrategy if omitted),
                  overridable per-search via ``strategy=`` kwarg.
    """

    _targets: list[tuple[OntologyRepository, str, str]]
    _strategy: SearchStrategy

    def __init__(
        self,
        router: AdapterRouter,
        scopes: list[tuple[str, str]],
        strategy: SearchStrategy | None = None,
    ) -> None:
        self._targets = [(router.get(b), b, s) for b, s in scopes]
        self._strategy = strategy or DirectStrategy()

    def search(
        self,
        *,
        keyword: str,
        search_scope: str = "all",
        result_per_type: int = 5,
        object_codes: list[str] | None = None,
        view_codes: list[str] | None = None,
        strategy: SearchStrategy | None = None,
    ) -> list[dict[str, Any]]:
        """Search across all cached scopes.

        Args:
            keyword: Search query string.
            search_scope: ``"metadata"`` / ``"instance"`` / ``"all"``.
            result_per_type: Max hits per result type per scene.
            object_codes: Real-time filter — restrict to these object codes.
            view_codes: Real-time filter — restrict to these view codes.
            strategy: Override the default strategy for this call.

        Returns:
            Deduplicated flat list of hit dicts, each carrying
            ``_base_id`` and ``_scene_id`` private tags.
        """
        strat = strategy or self._strategy
        raw = strat(
            keyword, self._targets,
            search_scope=search_scope, result_per_type=result_per_type,
            object_code=object_codes, view_code=view_codes,
        )
        return self._dedup(raw)

    def _dedup(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deduplicate by identity key; first occurrence wins."""
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for h in hits:
            key = _hit_identity(h)
            if key not in seen:
                seen.add(key)
                unique.append(h)
        return unique

"""Graph query profile configuration for term knowledge graph traversal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

GraphQueryProfile = Literal["graph_fast", "graph_deep", "graph_debug"]


@dataclass(frozen=True)
class GraphQueryOptions:
    """Derived query options from profile + explicit overrides."""

    query_profile: GraphQueryProfile
    max_level: int
    top_k: int
    max_candidates: int
    max_edges_per_root: int
    direction: str


GRAPH_QUERY_PROFILE_DEFAULTS: dict[GraphQueryProfile, GraphQueryOptions] = {
    "graph_fast": GraphQueryOptions(
        query_profile="graph_fast",
        max_level=1,
        top_k=20,
        max_candidates=5,
        max_edges_per_root=100,
        direction="both",
    ),
    "graph_deep": GraphQueryOptions(
        query_profile="graph_deep",
        max_level=2,
        top_k=50,
        max_candidates=10,
        max_edges_per_root=300,
        direction="both",
    ),
    "graph_debug": GraphQueryOptions(
        query_profile="graph_debug",
        max_level=1,
        top_k=50,
        max_candidates=20,
        max_edges_per_root=500,
        direction="both",
    ),
}


def _parse_query_profile(params: dict[str, Any]) -> GraphQueryProfile:
    """Parse and validate queryProfile parameter."""
    raw_profile = str(params.get("queryProfile", "graph_fast"))
    if raw_profile not in GRAPH_QUERY_PROFILE_DEFAULTS:
        raise ValueError(
            "queryProfile must be one of graph_fast, graph_deep, graph_debug"
        )
    return cast(GraphQueryProfile, raw_profile)


def _parse_search_level(raw_value: object, default_level: int) -> int:
    """Parse searchLevel with support for 0, all, and integers."""
    if raw_value is None:
        return default_level
    raw_text = str(raw_value)
    if raw_text == "0":
        return 0
    if raw_text == "all":
        return 999
    try:
        level = int(raw_text)
    except ValueError as exc:
        raise ValueError("searchLevel must be 0, all, or an integer") from exc
    if level < 0:
        raise ValueError("searchLevel must not be negative")
    return level


def _parse_max_candidates(raw_value: object, default_value: int) -> int:
    """Parse max_candidates with 1-20 range validation."""
    if raw_value is None:
        return default_value
    raw_text = str(raw_value)
    try:
        value = int(raw_text)
    except ValueError as exc:
        raise ValueError("max_candidates must be an integer between 1 and 20") from exc
    if value < 1 or value > 20:
        raise ValueError("max_candidates must be between 1 and 20")
    return value


def _resolve_graph_query_options(
    params: dict[str, Any],
    query_profile: GraphQueryProfile,
) -> GraphQueryOptions:
    """Resolve final query options from profile defaults + explicit overrides."""
    defaults = GRAPH_QUERY_PROFILE_DEFAULTS[query_profile]

    # Non-debug profiles block advanced override fields
    if query_profile != "graph_debug":
        blocked_debug_fields = [
            "direction",
            "maxEdgesPerRoot",
            "relationPageLimit",
            "relationTotalLimit",
            "relationTypes",
            "objectTypes",
        ]
        for field in blocked_debug_fields:
            if field in params:
                raise ValueError(
                    f"{field} is only allowed when queryProfile=graph_debug"
                )

    direction = defaults.direction
    max_edges_per_root = defaults.max_edges_per_root

    if query_profile == "graph_debug":
        direction = str(params.get("direction", defaults.direction))
        raw_max_edges = params.get("maxEdgesPerRoot", defaults.max_edges_per_root)
        try:
            max_edges_per_root = int(raw_max_edges)
        except (ValueError, TypeError) as exc:
            raise ValueError("maxEdgesPerRoot must be a positive integer") from exc

    return GraphQueryOptions(
        query_profile=query_profile,
        max_level=_parse_search_level(params.get("searchLevel"), defaults.max_level),
        top_k=defaults.top_k,
        max_candidates=_parse_max_candidates(
            params.get("max_candidates"),
            defaults.max_candidates,
        ),
        max_edges_per_root=max_edges_per_root,
        direction=direction,
    )

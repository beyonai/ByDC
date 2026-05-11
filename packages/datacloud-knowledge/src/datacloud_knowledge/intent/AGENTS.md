# AGENTS.md

**Module:** intent
**Purpose:** Recall, disambiguation, clarification, scoring, paradigm building

## OVERVIEW

Largest source domain in this package. Public consumers call service/facade functions while internals coordinate typed recall, BM25/vector/substring matching, shortest-path disambiguation, and multi-turn clarification.

## STRUCTURE

```text
intent/
├── service.py                 # External `*_with_session` service functions
├── batch_recall.py            # Batched typed recall and SQL/tsquery safety
├── typed_recall.py            # Type-partitioned recall facade
├── matching.py                # Mention matching helpers
├── disambiguation.py          # Disambiguation + shortest path graph/tree
├── clarification/             # Multi-turn clarification implementation
├── clarification_legacy.py    # Backward-compatible import path
├── paradigm_builder.py        # Five-stage paradigm state builder
├── llm_confirm.py             # Structured LLM confirmation models/helpers
├── score_update.py            # Score updates
├── storage.py                 # User term/knowledge writes
└── types.py                   # Shared public result/event types
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| External service functions | `service.py` | `*_with_session` naming pattern |
| Batched recall | `batch_recall.py` | Layered recall, fallback, tsquery safety |
| Multi-turn clarification | `clarification/api.py` | Main entry used by provider facade |
| Clarification finalization | `clarification/postprocess.py` | Normalize/apply resolved params |
| Confirmation retries | `clarification/confirm.py` | Structured LLM confirmation |
| Cartesian expansion | `clarification/cartesian.py` | Builds paradigm payload variants |
| Disambiguation | `disambiguation.py` | Shortest-path tree helpers |
| Paradigm resolution | `paradigm_builder.py` | `ParadigmResolutionState` |
| Tests | `tests/intent/` | Most package tests live here |

## PUBLIC SURFACE

`intent/__init__.py` exports 56 names, including `search_all_candidates_with_name_id`, `typed_multi_recall_with_session`, `disambiguate_with_session`, `analyze_query_clarification`, and score-update symbols. Treat these exports as compatibility-sensitive.

## CONVENTIONS

- Set `DATACLOUD_INTENT_DEBUG=1` to enable the package logger without changing root logging.
- Service APIs accept caller-managed SQLAlchemy sessions; do not open nested sessions in `*_with_session` paths.
- SQL uses bare table names and relies on DB connection/search-path setup.
- `batch_recall.py` must not pass raw user SQL/tsquery operators into `to_tsquery`; sanitize and parameterize.
- Vector recall is controlled by `DATACLOUD_INTENT_ENABLE_VECTOR` in service tests/runtime.

## ANTI-PATTERNS

- Do not remove legacy exports from `__init__.py` or `clarification_legacy.py` without downstream coordination.
- Do not add schema-qualified SQL here.
- Do not bypass clarification postprocess when persisting confirmed synonyms.
- Do not weaken retry/error behavior in `clarification/confirm.py`; tests cover retryable status handling.

## NOTES

- Existing TODO: ontology_code filtering in `clarification/api.py` remains incomplete.
- High-complexity files: `batch_recall.py`, `clarification/api.py`, `clarification/confirm.py`, `clarification/cartesian.py`, `paradigm_builder.py`, `disambiguation.py`.

# AGENTS.md

**Module:** knowledge_search
**Purpose:** Typed term, alias, object-property, and OWL-relation lookup facade

## OVERVIEW

`knowledge_search` is the read-side facade for consumers that need typed term search, alias resolution, property enum/value lookup, and related OWL terms. It bridges DB models and query search helpers.

## STRUCTURE

```text
knowledge_search/
├── __init__.py                # Public facade exports
├── term_search.py             # Typed search and alias/property lookup
├── owl_relation_resolver.py   # Related OWL term traversal
├── types.py                   # Result dataclasses/types
└── db/                        # Compatibility shims to datacloud_knowledge.db
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Search terms by type | `term_search.py:search_terms_by_type()` | Limit 1..200, offset >= 0 |
| Resolve field aliases | `term_search.py:resolve_field_aliases()` | Public via package `__init__` |
| Resolve values/aliases | `term_search.py:resolve_value_aliases()` | Uses term names/properties |
| Object properties | `term_search.py:get_object_props()` | ORM query facade |
| Related OWL terms | `owl_relation_resolver.py:resolve_related_owl_terms()` | Graph relation lookup |
| Public result types | `types.py` | `FieldResolutionResult`, `SearchTermsResult`, etc. |
| Compatibility DB imports | `db/` | Prefer new `datacloud_knowledge.db` imports elsewhere |

## PUBLIC SURFACE

`__init__.py` exports 15 names: typed search, field/value alias resolution, property getters, related-OWL resolver, and result dataclasses.

## CONVENTIONS

- Keep this module read-oriented. Writes belong in `intent/storage.py` or `knowledge_build/importer/writer.py`.
- Reuse `query.search.bm25_search_with_or` for keyword ranking rather than duplicating BM25 SQL.
- Validate pagination inputs at the facade boundary.
- `knowledge_search/db/*` exists for compatibility; new code should import from `datacloud_knowledge.db` directly.

## TESTS

| Area | Tests |
|------|-------|
| Field alias resolution | `tests/intent/test_resolve_field_aliases.py` |
| Provider facade usage | `tests/provider/test_provider.py` |

## ANTI-PATTERNS

- Do not add wildcard shim imports outside the existing `knowledge_search/db` compatibility files.
- Do not put schema-qualified SQL here; use shared DB context/session behavior.
- Do not mix provider-mode decisions into this module; `provider.py` owns that facade.

# AGENTS.md

**Module:** owl_gen
**Purpose:** Generate OWL import packages from business database schemas

## OVERVIEW

`owl_gen` reads configured table/schema metadata and renders the OWL package consumed by `knowledge_build.importer`. It is generation-side logic, not the importer.

## STRUCTURE

```text
owl_gen/
├── generator.py               # Main orchestration: read -> render -> write
├── schema_reader.py           # Source DB schema and term-value loading
├── models.py                  # Config/table/view/relation dataclasses
├── _xml.py                    # XML/text write helpers
└── renderers/
    ├── ontology.py            # object/mapping/dbsource/view files
    ├── term_types.py          # term type definitions/names
    ├── terms.py               # term value files
    ├── relations.py           # object/view/attribute relation files
    ├── meta.py                # package metadata
    └── manifest.py            # manifest output
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| End-to-end generation | `generator.py:generate()` | Reads source DB then writes package |
| Offline generation | `generator.py:generate_from_tables()` | No source DB connection |
| Source schema reading | `schema_reader.py` | Tables/columns/term values |
| Configuration models | `models.py:OwlGenConfig` | Public import from `owl_gen/__init__.py` |
| Renderer contracts | `renderers/*.py` | Keep XML templates out of `generator.py` |
| Multiview behavior | `tests/test_owl_gen_multiview.py` | Main regression coverage |

## CONVENTIONS

- `generator.py` orchestrates only. Put XML/text details in renderers or `_xml.py`.
- Renderers should return text; file-system writes are centralized through `_xml.write_text`.
- Public exports are defined in `owl_gen/__init__.py`; add exports there for supported SDK surface only.
- Generated package layout must remain compatible with `knowledge_build/importer/owl_parser.py` and converter tests.

## ANTI-PATTERNS

- Do not make renderers connect to databases.
- Do not make importer code depend on generator internals.
- Do not change output file names without updating importer tests and sample docs.

from __future__ import annotations

from importlib import import_module

import pytest


def _get_batch_module():  # type: ignore[no-untyped-def]
    return import_module("datacloud_knowledge.retrieval.recall._sql")


@pytest.mark.intent
@pytest.mark.parametrize(
    ("builder_name", "kwargs"),
    [
        (
            "_build_tsquery_sql",
            {
                "input_values": "(:keyword_key_0, :value_0)",
                "tsvector_column": "name_keywords",
                "order_expr": "score DESC",
                "type_filter": None,
                "scope_clause": "",
            },
        ),
        (
            "_build_substring_sql",
            {
                "input_values": "(:keyword_key_0, :value_0)",
                "type_filter": None,
                "scope_clause": "",
            },
        ),
    ],
)
def test_batch_recall_sql_uses_set_based_window_form(
    builder_name: str,
    kwargs: dict[str, object],
) -> None:
    batch_module = _get_batch_module()
    builder = getattr(batch_module, builder_name)

    stmt = builder(**kwargs)

    sql_text = str(stmt)
    assert "CROSS JOIN LATERAL" not in sql_text
    assert "LATERAL" not in sql_text
    assert "ROW_NUMBER() OVER" in sql_text
    assert "PARTITION BY i.keyword_key" in sql_text


@pytest.mark.intent
@pytest.mark.parametrize(
    ("builder_name", "kwargs"),
    [
        (
            "_build_tsquery_sql",
            {
                "input_values": "(:keyword_key_0, :value_0)",
                "tsvector_column": "name_keywords",
                "order_expr": "score DESC",
                "type_filter": frozenset({"project_status"}),
                "per_type_limit": 3,
                "scope_clause": "",
            },
        ),
        (
            "_build_substring_sql",
            {
                "input_values": "(:keyword_key_0, :value_0)",
                "type_filter": frozenset({"project_status"}),
                "per_type_limit": 3,
                "scope_clause": "",
            },
        ),
    ],
)
def test_batch_recall_per_type_sql_partitions_by_keyword_and_type(
    builder_name: str,
    kwargs: dict[str, object],
) -> None:
    batch_module = _get_batch_module()
    builder = getattr(batch_module, builder_name)

    stmt = builder(**kwargs)

    sql_text = str(stmt)
    assert "LATERAL" not in sql_text
    assert "PARTITION BY i.keyword_key, t.term_type_code" in sql_text
    assert "rn <= :per_type_limit" in sql_text

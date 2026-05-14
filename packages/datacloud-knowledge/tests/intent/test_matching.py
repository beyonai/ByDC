from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


def _get_matching_module() -> Any:
    return import_module("datacloud_knowledge.retrieval.mention_matching")


def _get_types_module() -> Any:
    return import_module("datacloud_knowledge.contracts.types")


def _get_cache_module() -> Any:
    return import_module("datacloud_knowledge.retrieval.name_cache")


@pytest.mark.intent
def test_match_mentions_exact_with_global_name_index() -> None:
    matching_module = _get_matching_module()
    types_module = _get_types_module()
    match_mentions = matching_module.match_mentions
    mention = types_module.Mention

    mentions = (mention(text="企业", role="ENTITY"),)
    global_index = {
        "企业": [("TERM_001", "OBJECT", "standard_name")],
    }

    result = match_mentions(
        mentions=mentions,
        session=None,
        global_name_index=global_index,
    )

    assert "企业" in result.exact
    candidates = result.exact["企业"]
    assert len(candidates) == 1
    assert candidates[0].term_id == "TERM_001"
    assert candidates[0].term_name == "企业"
    assert candidates[0].confidence == pytest.approx(1.0)
    assert candidates[0].score == pytest.approx(0.0)


@pytest.mark.intent
def test_match_mentions_with_user_id_none_uses_global_index_only() -> None:
    cache_module = _get_cache_module()
    matching_module = _get_matching_module()
    types_module = _get_types_module()
    user_name_cache = cache_module.UserNameCache
    match_mentions = matching_module.match_mentions
    mention = types_module.Mention

    mentions = (mention(text="税额", role="METRIC"),)
    global_index = {
        "税额": [("TERM_GLOBAL", "METRIC", "standard_name")],
    }
    user_cache = user_name_cache()
    user_cache.put(
        "user-1",
        {"税额": [("TERM_USER", "METRIC", "alias", 0.8)]},
    )

    result = match_mentions(
        mentions=mentions,
        session=None,
        user_id=None,
        global_name_index=global_index,
        user_cache=user_cache,
    )

    candidates = result.exact["税额"]
    assert len(candidates) == 1
    assert candidates[0].term_id == "TERM_GLOBAL"
    assert candidates[0].score == pytest.approx(0.0)


@pytest.mark.intent
def test_match_mentions_merges_global_and_user_cache_entries() -> None:
    cache_module = _get_cache_module()
    matching_module = _get_matching_module()
    types_module = _get_types_module()
    user_name_cache = cache_module.UserNameCache
    match_mentions = matching_module.match_mentions
    mention = types_module.Mention

    mentions = (mention(text="企业", role="ENTITY"),)
    global_index = {
        "企业": [
            ("TERM_001", "OBJECT", "standard_name"),
            ("TERM_002", "OBJECT", "alias"),
        ],
    }
    user_cache = user_name_cache()
    user_cache.put(
        "intent-user",
        {
            "企业": [
                ("TERM_002", "OBJECT", "alias", 0.7),
                ("TERM_003", "OBJECT", "alias", 0.9),
            ]
        },
    )

    result = match_mentions(
        mentions=mentions,
        session=None,
        user_id="intent-user",
        global_name_index=global_index,
        user_cache=user_cache,
    )

    candidates_by_term = {candidate.term_id: candidate for candidate in result.exact["企业"]}

    assert set(candidates_by_term) == {"TERM_001", "TERM_002", "TERM_003"}
    assert candidates_by_term["TERM_001"].confidence == pytest.approx(1.0)
    assert candidates_by_term["TERM_002"].score == pytest.approx(0.7)
    assert candidates_by_term["TERM_003"].score == pytest.approx(0.9)


@pytest.mark.intent
def test_match_mentions_unmatched_mention_goes_to_fuzzy_bucket() -> None:
    matching_module = _get_matching_module()
    types_module = _get_types_module()
    match_mentions = matching_module.match_mentions
    mention = types_module.Mention

    mentions = (mention(text="未知术语", role="ENTITY"),)

    result = match_mentions(
        mentions=mentions,
        session=None,
        global_name_index={"企业": [("TERM_001", "OBJECT", "standard_name")]},
    )

    assert "未知术语" not in result.exact
    assert result.fuzzy["未知术语"] == ()

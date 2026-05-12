from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _get_intent_module() -> Any:
    return import_module("datacloud_knowledge.intent")


def _get_types_module() -> Any:
    return import_module("datacloud_knowledge.intent.types")


@pytest.mark.intent
def test_clarification_result_legacy_mapping() -> None:
    clarification_result = _get_types_module().ClarificationResult
    result = clarification_result(query="q", needs_clarification=True, form="f", knowledge="k")

    assert result.to_legacy_dict() == {
        "query": "q",
        "complex_ask_user": True,
        "form": "f",
        "knowledge": "k",
    }

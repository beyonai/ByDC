"""Cartesian subpackage — Cartesian expansion and paradigmList building."""

from ._expand import MAX_COMBINATIONS, expand_condition_cartesian, truncate_candidates
from ._paradigm import (
    build_paradigm_list,
    serialize_knowledge_meta,
    serialize_paradigm_payload,
)

__all__ = [
    "MAX_COMBINATIONS",
    "build_paradigm_list",
    "expand_condition_cartesian",
    "serialize_knowledge_meta",
    "serialize_paradigm_payload",
    "truncate_candidates",
]

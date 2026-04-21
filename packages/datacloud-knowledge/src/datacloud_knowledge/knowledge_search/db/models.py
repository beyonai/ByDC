"""向后兼容 shim。"""

from datacloud_knowledge.db.models import *  # noqa: F403
from datacloud_knowledge.db.models import KNOWLEDGE_SCHEMA, Term, TermRelation, TermType

__all__ = ["KNOWLEDGE_SCHEMA", "Term", "TermRelation", "TermType"]

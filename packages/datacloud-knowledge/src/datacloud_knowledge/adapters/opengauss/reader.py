"""PostgresTermReader — Mixin-composed facade class.

All query methods are implemented in _readers/ Mixin files.
This facade combines them via multiple inheritance.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session

from ._readers._domain import _DomainReader
from ._readers._knowledge import _KnowledgeReader
from ._readers._library import _LibraryReader
from ._readers._name import _NameReader
from ._readers._relation import _RelationReader
from ._readers._term import _TermReader
from ._readers._term_type import _TermTypeReader


class PostgresTermReader(
    _DomainReader,
    _KnowledgeReader,
    _LibraryReader,
    _NameReader,
    _RelationReader,
    _TermReader,
    _TermTypeReader,
):
    """PostgreSQL TermReader implementation — Mixin composition."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
    ) -> None:
        super().__init__(session_factory=session_factory)

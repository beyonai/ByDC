"""PostgresTermWriter — Mixin-composed facade class.

All write methods are implemented in _writers/ Mixin files.
This facade combines them via multiple inheritance.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session

from ._writers._domain import _DomainWriter
from ._writers._knowledge import _KnowledgeWriter
from ._writers._library import _LibraryWriter
from ._writers._name import _NameWriter
from ._writers._relation import _RelationWriter
from ._writers._term import _TermWriter
from ._writers._term_type import _TermTypeWriter


class PostgresTermWriter(
    _DomainWriter,
    _KnowledgeWriter,
    _LibraryWriter,
    _TermWriter,
    _NameWriter,
    _RelationWriter,
    _TermTypeWriter,
):
    """PostgreSQL TermWriter implementation — Mixin composition."""

    def __init__(
        self,
        session: Session | None = None,
        session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
    ) -> None:
        super().__init__(session=session, session_factory=session_factory)

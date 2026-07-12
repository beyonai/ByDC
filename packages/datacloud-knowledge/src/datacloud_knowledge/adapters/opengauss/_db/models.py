from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Term(Base):
    __tablename__ = "term"

    term_id: Mapped[str] = mapped_column(String(1000), primary_key=True)
    term_code: Mapped[str] = mapped_column(String(255), nullable=False)
    term_name: Mapped[str] = mapped_column(String(255), nullable=False)
    desc_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_term_id: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    owl_doc_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    domain_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    term_type_code: Mapped[str] = mapped_column(String(32), nullable=False)
    library_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    term_tags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class TermRelation(Base):
    __tablename__ = "term_relation"

    relation_id: Mapped[str] = mapped_column(String(1000), primary_key=True)
    source_term_id: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_term_type_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_term_id: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    target_term_type_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    relation_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relation_category: Mapped[str] = mapped_column(String(16), nullable=False)
    cardinality: Mapped[str | None] = mapped_column(String(8), nullable=True)
    action_term_id: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class TermType(Base):
    __tablename__ = "term_type"

    type_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type_code: Mapped[str] = mapped_column(String(32), nullable=False)
    type_name: Mapped[str] = mapped_column(String(255), nullable=False)
    type_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_category: Mapped[int] = mapped_column(nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    library_id: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class TermName(Base):
    __tablename__ = "term_name"

    name_id: Mapped[str] = mapped_column(String(1000), primary_key=True)
    term_id: Mapped[str] = mapped_column(String(1000), nullable=False)
    name_text: Mapped[str] = mapped_column(String(255), nullable=False)
    search_scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class TermKnowledge(Base):
    __tablename__ = "term_knowledge"

    knowledge_id: Mapped[str] = mapped_column(String(1000), primary_key=True)
    term_id: Mapped[str] = mapped_column(String(1000), nullable=False)
    desc_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    ext_system: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ext_kb_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ext_doc_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Domain(Base):
    __tablename__ = "domain"

    domain_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    domain_name: Mapped[str] = mapped_column(String(255))
    parent_id: Mapped[str | None] = mapped_column(String(64))
    domain_desc: Mapped[str | None] = mapped_column(Text)
    created_time: Mapped[datetime] = mapped_column(DateTime)
    updated_time: Mapped[datetime] = mapped_column(DateTime)


class TermLibrary(Base):
    __tablename__ = "term_library"

    library_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    library_code: Mapped[str] = mapped_column(String(32))
    library_name: Mapped[str] = mapped_column(String(255))
    created_time: Mapped[datetime] = mapped_column(DateTime)
    updated_time: Mapped[datetime] = mapped_column(DateTime)


class DomainLibrary(Base):
    __tablename__ = "domain_library"

    domain_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    library_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class TermDomain(Base):
    """术语领域表 — 替换 domain + domain_library + domain_term_type 三表。"""

    __tablename__ = "term_domain"

    domain_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    domain_code: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    library_id: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class DomainTermType(Base):
    __tablename__ = "domain_term_type"

    domain_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type_code: Mapped[str] = mapped_column(String(32), primary_key=True)

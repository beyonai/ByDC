from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from datacloud_knowledge.db_url import resolve_knowledge_schema

KNOWLEDGE_SCHEMA = resolve_knowledge_schema()


class Base(DeclarativeBase):
    pass


class Term(Base):
    __tablename__ = "term"
    __table_args__ = {"schema": KNOWLEDGE_SCHEMA}

    term_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    term_code: Mapped[str] = mapped_column(String(255), nullable=False)
    term_name: Mapped[str] = mapped_column(String(255), nullable=False)
    desc_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_term_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owl_doc_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    domain_id: Mapped[str] = mapped_column(String(64), nullable=False)
    term_type_code: Mapped[str] = mapped_column(String(32), nullable=False)
    library_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    term_tags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class TermRelation(Base):
    __tablename__ = "term_relation"
    __table_args__ = {"schema": KNOWLEDGE_SCHEMA}

    relation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_term_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_term_id: Mapped[str] = mapped_column(String(64), nullable=False)
    relation_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relation_category: Mapped[str] = mapped_column(String(16), nullable=False)
    cardinality: Mapped[str | None] = mapped_column(String(8), nullable=True)
    action_term_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class TermType(Base):
    __tablename__ = "term_type"
    __table_args__ = {"schema": KNOWLEDGE_SCHEMA}

    type_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    type_name: Mapped[str] = mapped_column(String(255), nullable=False)
    type_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_category: Mapped[int] = mapped_column(nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TermName(Base):
    __tablename__ = "term_name"
    __table_args__ = {"schema": KNOWLEDGE_SCHEMA}

    name_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    term_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name_text: Mapped[str] = mapped_column(String(255), nullable=False)
    search_scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class TermKnowledge(Base):
    __tablename__ = "term_knowledge"
    __table_args__ = {"schema": KNOWLEDGE_SCHEMA}

    knowledge_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    term_id: Mapped[str] = mapped_column(String(255), nullable=False)
    desc_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    ext_system: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ext_kb_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ext_doc_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)

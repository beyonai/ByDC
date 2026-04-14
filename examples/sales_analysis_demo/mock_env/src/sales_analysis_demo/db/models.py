"""SQLAlchemy 表映射，基于 DDL.sql."""

from datetime import datetime
import os

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base."""

    pass


# ---------------------------------------------------------------------------
# crm_demo schema（组织、用户表固定在 crm_demo）
# ---------------------------------------------------------------------------


class PoOrganization(Base):
    """组织表 crm_demo.po_organization."""

    __tablename__ = "po_organization"
    __table_args__ = {"schema": "crm_demo"}

    org_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_code: Mapped[str] = mapped_column(String(250), nullable=False)
    org_name: Mapped[str] = mapped_column(String(100), nullable=False)
    org_type: Mapped[str] = mapped_column(String(4), nullable=False, default="0")
    parent_org_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    org_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    org_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    create_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    path_code: Mapped[str | None] = mapped_column(String(500), nullable=True)
    org_desc: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class PoUsersOrganization(Base):
    """用户组织关联表 crm_demo.po_users_organization."""

    __tablename__ = "po_users_organization"
    __table_args__ = {"schema": "crm_demo"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_type: Mapped[str | None] = mapped_column(String(50), nullable=True)


class PoUsers(Base):
    """用户表 crm_demo.po_users."""

    __tablename__ = "po_users"
    __table_args__ = {"schema": "crm_demo"}

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_code: Mapped[str] = mapped_column(String(255), nullable=False)
    pwd: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_eff_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_exp_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    create_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    update_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    state: Mapped[str] = mapped_column(String(1), nullable=False, default="A")
    state_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_locked: Mapped[str] = mapped_column(String(1), nullable=False)
    last_login_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    security_question_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    security_answer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    thumbnail_uri: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ext_attr: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    assistant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    station_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    register_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    apple_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


# ---------------------------------------------------------------------------
# 待办相关表：schema 可配置（默认 crm_demo）
# ---------------------------------------------------------------------------

TODO_SCHEMA = os.getenv("DATACLOUD_TODO_SCHEMA", "crm_demo")


class TodoItems(Base):
    """待办主表 search.todo_items."""

    __tablename__ = "todo_items"
    __table_args__ = {"schema": TODO_SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    todo_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    todo_priority: Mapped[str | None] = mapped_column(String(64), nullable=True, default="Normal")
    todo_status: Mapped[str | None] = mapped_column(String(64), nullable=True, default="Pending")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    promoter: Mapped[str] = mapped_column(String(64), nullable=False)
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    handler_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    meeting_note_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    return_reason: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TodoItemHandlers(Base):
    """待办处理人关联表 search.todo_item_handlers."""

    __tablename__ = "todo_item_handlers"
    __table_args__ = {"schema": TODO_SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    todo_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    handler_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handle_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)


# ---------------------------------------------------------------------------
# public schema (sales_expense_report)
# ---------------------------------------------------------------------------


class SalesExpenseReport(Base):
    """费用报备表 public.sales_expense_report."""

    __tablename__ = "sales_expense_report"
    __table_args__ = {"schema": "crm_demo"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    applicant_emp_no: Mapped[str] = mapped_column(String(32), nullable=False)
    applicant_name: Mapped[str] = mapped_column(String(64), nullable=False)
    applicant_org_id: Mapped[str] = mapped_column(String(32), nullable=False)
    expense_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    expense_desc: Mapped[str | None] = mapped_column(String(512), nullable=True)
    related_bo_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    apply_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default="PENDING"
    )
    approval_comment: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

"""Database tables for QE Connect."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, TypeDecorator, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TZDateTime(TypeDecorator):
    """Timezone-aware datetimes on every database (SQLite drops tzinfo); stored as UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            value = value.astimezone(timezone.utc)
            if dialect.name == "sqlite":
                value = value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="editor")  # admin | editor | viewer
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime(), nullable=True)
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mfa_pending_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mfa_last_step: Mapped[int] = mapped_column(Integer, default=0)


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime())
    last_seen_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    mfa_state: Mapped[str] = mapped_column(String(10), default="ok")  # ok | verify | setup
    user: Mapped[User] = relationship()


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Lob(Base):
    __tablename__ = "lobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    project_id: Mapped[str] = mapped_column(String(80), default="")
    lob_id: Mapped[Optional[int]] = mapped_column(ForeignKey("lobs.id", ondelete="SET NULL"), nullable=True, index=True)
    team: Mapped[str] = mapped_column(String(200), default="")
    respondent_name: Mapped[str] = mapped_column(String(200), default="")
    respondent_email: Mapped[str] = mapped_column(String(254), default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)
    lob: Mapped[Optional[Lob]] = relationship()
    invitation: Mapped[Optional["Invitation"]] = relationship(back_populates="application", uselist=False, cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    qid: Mapped[str] = mapped_column(String(20), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    section: Mapped[str] = mapped_column(String(200), default="General")
    pillar: Mapped[str] = mapped_column(String(200), default="")
    focus: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text)
    help: Mapped[str] = mapped_column(Text, default="")
    rtype: Mapped[str] = mapped_column(String(20), default="short")  # short long single multi number
    options: Mapped[list] = mapped_column(JSON, default=list)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    core: Mapped[bool] = mapped_column(Boolean, default=True)
    show_if: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text, default="")
    dimension: Mapped[str] = mapped_column(String(200), default="")


class Invitation(Base):
    """The survey for one application: its link, status and answers."""

    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("application_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent opened progress completed
    mode: Mapped[str] = mapped_column(String(10), default="core")  # core | all
    due_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime(), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    opened_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime(), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime(), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime(), nullable=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    other: Mapped[dict] = mapped_column(JSON, default=dict)
    prefilled: Mapped[list] = mapped_column(JSON, default=list)
    reminders: Mapped[int] = mapped_column(Integer, default=0)
    reference: Mapped[str] = mapped_column(String(20), default="")
    application: Mapped[Application] = relationship(back_populates="invitation")


class Email(Base):
    __tablename__ = "emails"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[Optional[int]] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20))  # Invitation | Reminder | Test
    to_addr: Mapped[str] = mapped_column(String(254))
    to_name: Mapped[str] = mapped_column(String(200), default="")
    from_addr: Mapped[str] = mapped_column(String(320), default="")
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued sent recorded failed
    via: Mapped[str] = mapped_column(String(20), default="sim")
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime(), nullable=True)
    created_by: Mapped[str] = mapped_column(String(254), default="")


class Activity(Base):
    __tablename__ = "activity"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(254), default="")
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(Text, default="")


class SecurityEvent(Base):
    """Security log: sign-ins, sign-outs, MFA, account and permission changes, exports and deletions."""

    __tablename__ = "security_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    outcome: Mapped[str] = mapped_column(String(12), default="ok")  # ok | fail | blocked
    actor: Mapped[str] = mapped_column(String(254), default="", index=True)
    ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    detail: Mapped[str] = mapped_column(Text, default="")

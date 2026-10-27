"""Writing to and reading from the security log."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import timedelta

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import SecurityEvent, utcnow

CURRENT_IP: ContextVar[str] = ContextVar("qec_client_ip", default="")
WINDOW_MINUTES = 15
ACCOUNT_LIMIT = 5
ADDRESS_LIMIT = 20


def client_ip(request: Request | None) -> str:
    if request is None or request.client is None:
        return CURRENT_IP.get()
    return (request.client.host or "")[:64]


def record(db: Session, kind: str, actor: str = "", request: Request | None = None, outcome: str = "ok",
           detail: str = "", ip: str | None = None) -> None:
    db.add(SecurityEvent(kind=kind, outcome=outcome, actor=(actor or "")[:254], ip=ip if ip is not None else client_ip(request),
                         detail=(detail or "")[:2000]))


def _failures(db: Session, column, value: str) -> int:
    since = utcnow() - timedelta(minutes=WINDOW_MINUTES)
    last_ok = db.scalar(select(func.max(SecurityEvent.at)).where(
        SecurityEvent.kind == "signin", SecurityEvent.outcome == "ok", column == value, SecurityEvent.at >= since))
    q = select(func.count(SecurityEvent.id)).where(
        SecurityEvent.kind.in_(("signin", "mfa.verify")), SecurityEvent.outcome == "fail", column == value,
        SecurityEvent.at >= (last_ok if last_ok and last_ok > since else since))
    return db.scalar(q) or 0


def signin_blocked(db: Session, email: str, ip: str) -> bool:
    """Throttle from the security log: per account and per client address, since the last success."""
    return _failures(db, SecurityEvent.actor, email) >= ACCOUNT_LIMIT or (
        bool(ip) and _failures(db, SecurityEvent.ip, ip) >= ADDRESS_LIMIT)

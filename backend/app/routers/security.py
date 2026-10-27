"""Security policy (MFA requirement, idle timeout) and the security log (administrators only)."""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SecurityEvent, User, utcnow
from ..security import is_admin
from ..services import seclog, store
from ..services.export import safe

router = APIRouter(prefix="/api/security", tags=["security"])


class PolicyIn(BaseModel):
    mfa_required: bool
    idle_minutes: int = Field(30, ge=0, le=720)


@router.get("/policy")
def get_policy(db: Session = Depends(get_db), _: User = Depends(is_admin)):
    users = db.scalars(select(User).where(User.active.is_(True))).all()
    return {**store.get(db, "security"), "users_without_mfa": [u.email for u in users if not u.mfa_secret]}


@router.put("/policy")
def put_policy(body: PolicyIn, request: Request, db: Session = Depends(get_db), me: User = Depends(is_admin)):
    before = store.get(db, "security")
    store.put(db, "security", body.model_dump())
    seclog.record(db, "policy.change", me.email, request,
                  detail=f"MFA required: {before.get('mfa_required')} → {body.mfa_required}; idle minutes: "
                         f"{before.get('idle_minutes')} → {body.idle_minutes}")
    db.commit()
    return get_policy(db, me)


def _query(kind: Optional[str], outcome: Optional[str], q: Optional[str]):
    stmt = select(SecurityEvent).order_by(SecurityEvent.id.desc())
    if kind:
        stmt = stmt.where(SecurityEvent.kind.startswith(kind))
    if outcome:
        stmt = stmt.where(SecurityEvent.outcome == outcome)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(SecurityEvent.actor.ilike(like), SecurityEvent.ip.ilike(like), SecurityEvent.detail.ilike(like)))
    return stmt


def _out(e: SecurityEvent) -> dict:
    return {"id": e.id, "at": e.at.isoformat(), "kind": e.kind, "outcome": e.outcome, "actor": e.actor, "ip": e.ip, "detail": e.detail}


@router.get("/events")
def events(kind: Optional[str] = None, outcome: Optional[str] = None, q: Optional[str] = None,
           limit: int = Query(300, ge=1, le=2000), db: Session = Depends(get_db), _: User = Depends(is_admin)):
    return [_out(e) for e in db.scalars(_query(kind, outcome, q).limit(limit))]


@router.get("/events/download")
def events_csv(request: Request, kind: Optional[str] = None, outcome: Optional[str] = None, q: Optional[str] = None,
               db: Session = Depends(get_db), me: User = Depends(is_admin)):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["When (UTC)", "Event", "Outcome", "Who", "Address", "Details"])
    for e in db.scalars(_query(kind, outcome, q).limit(100000)):
        w.writerow([e.at.strftime("%Y-%m-%d %H:%M:%S"), e.kind, e.outcome, safe(e.actor), e.ip, safe(e.detail)])
    seclog.record(db, "export.securitylog", me.email, request)
    db.commit()
    return Response(("﻿" + buf.getvalue()).encode(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="QE_Connect_security_log_{utcnow():%Y-%m-%d}.csv"'})

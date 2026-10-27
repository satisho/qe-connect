"""Tracker: sending invitations and reminders, following progress, viewing and downloading responses."""
from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Activity, Application, Email, Invitation, Question, User, utcnow
from ..security import can_edit, can_view
from ..services import export, mail, rules, sample, seclog, store
from .setup import lob_names

router = APIRouter(prefix="/api", tags=["tracker"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _questions(db: Session) -> list[Question]:
    return list(db.scalars(select(Question).order_by(Question.position, Question.id)))


@router.get("/tracker")
def tracker(db: Session = Depends(get_db), user: User = Depends(can_view)):
    qs = _questions(db)
    apps = db.scalars(select(Application).order_by(func.lower(Application.name), Application.id)).all()
    failed = {e.application_id for e in db.scalars(select(Email).where(Email.status == "failed"))}
    rows = []
    counts = {k: 0 for k in ("notsent", "sent", "opened", "progress", "completed")}
    for a in apps:
        inv = a.invitation
        status = inv.status if inv else "notsent"
        counts[status] += 1
        d, n = rules.progress(qs, inv.mode, inv.answers or {}, inv.other or {}) if inv else (0, 0)
        rows.append({
            "id": a.id, "name": a.name, "project_id": a.project_id, "lob": a.lob.name if a.lob else "",
            "lob_id": a.lob_id, "team": a.team, "respondent_name": a.respondent_name,
            "respondent_email": a.respondent_email, "email_ok": mail.email_ok(a.respondent_email), "status": status,
            "answered": d, "total": n, "mode": inv.mode if inv else None,
            "due_at": iso(inv.due_at) if inv else None, "sent_at": iso(inv.sent_at) if inv else None,
            "opened_at": iso(inv.opened_at) if inv else None, "completed_at": iso(inv.completed_at) if inv else None,
            "reminders": inv.reminders if inv else 0, "email_failed": a.id in failed,
            **({"link": mail.survey_link(db, inv.token)} if inv and user.role != "viewer" else {}),
        })
    d = store.get(db, "delivery")
    return {"applications": rows, "counts": counts, "total": len(rows),
            "delivery": {"mode": d.get("mode"), "mailbox": d.get("mailbox"), "tested": bool((d.get("tested") or {}).get("ok")),
                         "rate_per_minute": d.get("rate_per_minute")},
            "default_due_days": store.get(db, "campaign").get("default_due_days", 14)}


class SendIn(BaseModel):
    application_ids: list[int]
    due_date: Optional[date] = None


class IdsIn(BaseModel):
    application_ids: list[int]


def _due(d: Optional[date], days: int) -> datetime:
    d = d or (utcnow() + timedelta(days=days)).date()
    return datetime.combine(d, time(23, 59), tzinfo=timezone.utc)


@router.post("/invitations/send")
def send(body: SendIn, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    if body.due_date and body.due_date < utcnow().date():
        raise HTTPException(422, "The respond-by date is in the past.")
    days = store.get(db, "campaign").get("default_due_days", 14)
    sent, skipped = [], []
    for aid in dict.fromkeys(body.application_ids):
        a = db.get(Application, aid)
        if not a:
            continue
        if not mail.email_ok(a.respondent_email):
            skipped.append({"name": a.name, "reason": "no valid respondent email"})
            continue
        inv = a.invitation
        if inv and inv.status == "completed":
            skipped.append({"name": a.name, "reason": "already completed"})
            continue
        if not inv:
            inv = Invitation(application_id=a.id, token=secrets.token_urlsafe(18), status="sent", mode="core",
                             answers={}, other={}, prefilled=[], sent_at=utcnow(), reference=sample.new_reference())
            db.add(inv)
            a.invitation = inv
        inv.due_at = _due(body.due_date, days)
        db.flush()
        mail.compose(db, a, inv, "Invitation", me.email)
        sent.append(a.name)
    if sent:
        store.log(db, me.email, "invite.send", f"{len(sent)} invitation(s): {', '.join(sent)[:500]}")
    db.commit()
    return {"sent": len(sent), "skipped": skipped, "delivery": store.get(db, "delivery").get("mode")}


@router.post("/invitations/remind")
def remind(body: IdsIn, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    done, skipped = [], []
    for aid in dict.fromkeys(body.application_ids):
        a = db.get(Application, aid)
        if not a:
            continue
        inv = a.invitation
        if not inv or inv.status == "completed":
            skipped.append({"name": a.name, "reason": "not waiting for a response"})
            continue
        if not mail.email_ok(a.respondent_email):
            skipped.append({"name": a.name, "reason": "no valid respondent email"})
            continue
        inv.reminders += 1
        mail.compose(db, a, inv, "Reminder", me.email)
        done.append(a.name)
    if done:
        store.log(db, me.email, "invite.remind", ", ".join(done)[:500])
    db.commit()
    return {"sent": len(done), "skipped": skipped}


@router.post("/invitations/{aid}/reopen")
def reopen(aid: int, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    a = db.get(Application, aid)
    if not a or not a.invitation or a.invitation.status != "completed":
        raise HTTPException(409, "Only a completed response can be reopened.")
    a.invitation.status = "progress"
    a.invitation.completed_at = None
    store.log(db, me.email, "invite.reopen", f"Reopened the response for {a.name}")
    seclog.record(db, "response.reopen", me.email, detail=a.name)
    db.commit()
    return {"ok": True}


@router.delete("/invitations/{aid}")
def withdraw(aid: int, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    """Cancel a survey link that hasn't been completed (for example sent to the wrong person)."""
    a = db.get(Application, aid)
    if not a or not a.invitation:
        raise HTTPException(404, "There's no survey for this application.")
    if a.invitation.status == "completed":
        raise HTTPException(409, "This response is complete. Reopen it instead.")
    db.delete(a.invitation)
    store.log(db, me.email, "invite.withdraw", f"Cancelled the survey link for {a.name}")
    seclog.record(db, "delete.surveylink", me.email, detail=f"Cancelled the survey link for {a.name}")
    db.commit()
    return {"ok": True}


def _completed(db: Session, aid: int) -> Application:
    a = db.get(Application, aid)
    if not a or not a.invitation:
        raise HTTPException(404, "There's no response for this application yet.")
    return a


@router.get("/responses/{aid}")
def response(aid: int, db: Session = Depends(get_db), _: User = Depends(can_view)):
    a = _completed(db, aid)
    inv = a.invitation
    qs = _questions(db)
    lobs = lob_names(db)
    vis = rules.visible(qs, inv.mode, inv.answers or {})
    sections = []
    for q in vis:
        sid, sname = rules.section_parts(q.section)
        if not sections or sections[-1]["key"] != q.section:
            sections.append({"key": q.section, "id": sid, "name": sname, "items": []})
        sections[-1]["items"].append({"qid": q.qid, "text": q.text,
                                      "answer": rules.format_answer(q, inv.answers or {}, inv.other or {}),
                                      "required": q.required})
    return {"application": {"id": a.id, "name": a.name, "lob": a.lob.name if a.lob else "",
                            "respondent_name": a.respondent_name, "respondent_email": a.respondent_email},
            "status": inv.status, "mode": inv.mode, "completed_at": iso(inv.completed_at), "sections": sections,
            "lobs": lobs}


def _fname(s: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") or "application"


@router.get("/responses/{aid}/download")
def download_one(aid: int, fmt: str = Query("xlsx", pattern="^(xlsx|csv)$"), db: Session = Depends(get_db),
                 me: User = Depends(can_view)):
    a = _completed(db, aid)
    if a.invitation.status != "completed":
        raise HTTPException(409, "This response isn't complete yet.")
    data = export.one_response(a, _questions(db), fmt)
    store.log(db, me.email, "response.download", f"{a.name} ({fmt})")
    seclog.record(db, "export.response", me.email, detail=f"{a.name} ({fmt})")
    db.commit()
    return Response(data, media_type=XLSX if fmt == "xlsx" else "text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="QE_Connect_{_fname(a.name)}.{fmt}"'})


@router.get("/responses-all/download")
def download_all(fmt: str = Query("xlsx", pattern="^(xlsx|csv)$"), db: Session = Depends(get_db),
                 me: User = Depends(can_view)):
    apps = [a for a in db.scalars(select(Application).order_by(func.lower(Application.name))) if a.invitation and a.invitation.status == "completed"]
    if not apps:
        raise HTTPException(404, "No completed responses yet.")
    data = export.all_responses(apps, _questions(db), fmt)
    store.log(db, me.email, "response.export", f"{len(apps)} completed responses ({fmt})")
    seclog.record(db, "export.responses", me.email, detail=f"{len(apps)} completed responses ({fmt})")
    db.commit()
    stamp = utcnow().strftime("%Y-%m-%d")
    return Response(data, media_type=XLSX if fmt == "xlsx" else "text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="QE_Connect_responses_{stamp}.{fmt}"'})


@router.get("/emails")
def emails(limit: int = Query(300, le=2000), db: Session = Depends(get_db), _: User = Depends(can_view)):
    rows = db.scalars(select(Email).order_by(Email.id.desc()).limit(limit)).all()
    names = {a.id: a.name for a in db.scalars(select(Application))}
    return [{"id": e.id, "application_id": e.application_id, "application": names.get(e.application_id, ""),
             "kind": e.kind, "to": f"{e.to_name} <{e.to_addr}>" if e.to_name else e.to_addr, "from": e.from_addr,
             "subject": e.subject, "body": e.body, "status": e.status, "via": e.via, "error": e.error,
             "created_at": iso(e.created_at), "sent_at": iso(e.sent_at)} for e in rows]


@router.post("/emails/{eid}/retry")
def retry(eid: int, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    e = db.get(Email, eid)
    if not e or e.status != "failed":
        raise HTTPException(409, "Only a failed email can be sent again.")
    e.status, e.attempts, e.error = "queued", 0, ""
    store.log(db, me.email, "email.retry", f"{e.kind} to {e.to_addr}")
    db.commit()
    return {"ok": True}


@router.get("/activity")
def activity(limit: int = Query(200, le=1000), db: Session = Depends(get_db), _: User = Depends(can_view)):
    rows = db.scalars(select(Activity).order_by(Activity.id.desc()).limit(limit)).all()
    return [{"id": r.id, "at": iso(r.at), "actor": r.actor, "action": r.action, "detail": r.detail} for r in rows]

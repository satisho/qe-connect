"""The respondent's side: the survey behind each emailed link. No sign-in; the link's token is the key."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Invitation, Question, utcnow
from ..services import rules, sample, store
from .setup import lob_names, q_out
from .tracker import iso

router = APIRouter(prefix="/api/s", tags=["survey"])
ORDER = ["sent", "opened", "progress", "completed"]


class SaveIn(BaseModel):
    answers: dict = Field(default_factory=dict)
    other: dict = Field(default_factory=dict)
    mode: Literal["core", "all"] = "core"


def _inv(db: Session, token: str) -> Invitation:
    if not token or len(token) > 64:
        raise HTTPException(404, "This survey link isn't valid.")
    inv = db.scalar(select(Invitation).where(Invitation.token == token))
    if not inv:
        raise HTTPException(404, "This survey link isn't valid. It may have been cancelled or replaced; "
                                 f"ask the {store.org(db)['team_name']} for a new one.")
    return inv


def _qs(db: Session):
    return list(db.scalars(select(Question).order_by(Question.position, Question.id)))


def _bump(inv: Invitation, status: str) -> None:
    if ORDER.index(status) > ORDER.index(inv.status):
        inv.status = status


def _out(db: Session, inv: Invitation) -> dict:
    a = inv.application
    lobs = lob_names(db)
    return {
        "application": {"name": a.name, "lob": a.lob.name if a.lob else "", "team": a.team,
                        "respondent_name": a.respondent_name},
        "campaign": store.get(db, "campaign")["name"],
        "organization": store.org(db),
        "status": inv.status, "mode": inv.mode, "due_at": iso(inv.due_at), "completed_at": iso(inv.completed_at),
        "reference": inv.reference,
        "questions": [{**q_out(q), "options": rules.options_for(q, lobs)} for q in _qs(db)],
        "answers": inv.answers or {}, "other": inv.other or {}, "prefilled": inv.prefilled or [],
    }


@router.get("/{token}")
def open_survey(token: str, db: Session = Depends(get_db)):
    inv = _inv(db, token)
    if not inv.opened_at:
        inv.opened_at = utcnow()
        pre, oth = sample.prefill(inv.application, _qs(db))
        inv.answers = {**pre, **(inv.answers or {})}
        inv.other = {**oth, **(inv.other or {})}
        inv.prefilled = list(pre)
        _bump(inv, "opened")
        store.log(db, inv.application.respondent_email or "respondent", "survey.open", inv.application.name)
        db.commit()
    return _out(db, inv)


@router.put("/{token}")
def save(token: str, body: SaveIn, db: Session = Depends(get_db)):
    inv = _inv(db, token)
    if inv.status == "completed":
        raise HTTPException(409, f"This survey has already been submitted. Ask the {store.org(db)['team_name']} to reopen it.")
    answers, other = rules.clean_answers(_qs(db), lob_names(db), body.answers, body.other)
    inv.answers, inv.other, inv.mode = answers, other, body.mode
    if not inv.started_at:
        inv.started_at = utcnow()
    _bump(inv, "progress")
    db.commit()
    return {"ok": True, "saved_at": utcnow().isoformat()}


@router.post("/{token}/submit")
def submit(token: str, body: SaveIn, db: Session = Depends(get_db)):
    inv = _inv(db, token)
    if inv.status == "completed":
        return _out(db, inv)
    qs = _qs(db)
    answers, other = rules.clean_answers(qs, lob_names(db), body.answers, body.other)
    vis = rules.visible(qs, body.mode, answers)
    problems = [{"qid": q.qid, "message": m} for q in vis if (m := rules.problem(q, answers, other))]
    inv.answers, inv.other, inv.mode = answers, other, body.mode
    if problems:
        db.commit()
        raise HTTPException(422, {"message": f"{len(problems)} question(s) still need an answer.", "problems": problems})
    inv.status = "completed"
    inv.completed_at = utcnow()
    inv.started_at = inv.started_at or inv.completed_at
    store.log(db, inv.application.respondent_email or "respondent", "survey.submit", inv.application.name)
    db.commit()
    return _out(db, inv)

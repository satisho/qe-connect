"""Setup: lines of business, applications with respondents, and the question bank."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, Lob, Question, User
from ..security import can_edit, can_view
from ..services import export, importer, rules, seclog, store
from ..services.mail import email_ok, one_line

router = APIRouter(prefix="/api", tags=["setup"])
MAX_UPLOAD = 10 * 1024 * 1024


def lob_out(x: Lob, counts: dict) -> dict:
    return {"id": x.id, "name": x.name, "position": x.position, "applications": counts.get(x.id, 0)}


def app_out(a: Application) -> dict:
    return {"id": a.id, "name": a.name, "project_id": a.project_id, "lob_id": a.lob_id,
            "lob": a.lob.name if a.lob else "", "team": a.team, "respondent_name": a.respondent_name,
            "respondent_email": a.respondent_email, "status": a.invitation.status if a.invitation else "notsent"}


def rule_info(q: Question) -> dict | None:
    r = rules.parse_rule(q.show_if)
    if not r:
        return None
    if r.kind == "lobs":
        return {"kind": "lobs"}
    if r.kind == "bad":
        return {"kind": "bad"}
    return {"kind": "match", "qid": r.qid, "negate": r.negate, "values": len(r.values), "match": list(r.values)}


def q_out(q: Question) -> dict:
    return {"id": q.id, "qid": q.qid, "position": q.position, "section": q.section, "pillar": q.pillar,
            "focus": q.focus, "text": q.text, "help": q.help, "rtype": q.rtype, "options": q.options or [],
            "required": q.required, "core": q.core, "show_if": q.show_if, "source": q.source,
            "dimension": q.dimension, "rule": rule_info(q)}


async def _tables(file: Optional[UploadFile], text: Optional[str]):
    if file is not None and file.filename:
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "That file is larger than 10 MB.")
        try:
            return importer.read_tables(file.filename, data)
        except importer.ImportProblem as exc:
            raise HTTPException(422, str(exc)) from exc
    if text and text.strip():
        return [("pasted", importer.parse_text(text))]
    raise HTTPException(422, "Choose a file or paste some rows first.")


# ---------------------------------------------------------------- lines of business
class LobIn(BaseModel):
    name: str


@router.get("/lobs")
def list_lobs(db: Session = Depends(get_db), _: User = Depends(can_view)):
    counts = dict(db.execute(select(Application.lob_id, func.count(Application.id)).group_by(Application.lob_id)).all())
    return [lob_out(x, counts) for x in db.scalars(select(Lob).order_by(Lob.position, Lob.id))]


@router.post("/lobs")
def add_lob(body: LobIn, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    name = one_line(body.name)[:200]
    if not name:
        raise HTTPException(422, "Enter a name.")
    if db.scalar(select(Lob).where(func.lower(Lob.name) == name.lower())):
        raise HTTPException(409, "That line of business is already on the list.")
    pos = (db.scalar(select(func.max(Lob.position))) or 0) + 1
    db.add(Lob(name=name, position=pos))
    store.log(db, me.email, "lob.add", name)
    db.commit()
    return {"ok": True}


@router.patch("/lobs/{lid}")
def rename_lob(lid: int, body: LobIn, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    x = db.get(Lob, lid)
    if not x:
        raise HTTPException(404, "No such line of business.")
    name = one_line(body.name)[:200]
    if not name:
        raise HTTPException(422, "Enter a name.")
    store.log(db, me.email, "lob.rename", f"{x.name} → {name}")
    x.name = name
    db.commit()
    return {"ok": True}


@router.delete("/lobs/{lid}")
def delete_lob(lid: int, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    x = db.get(Lob, lid)
    if not x:
        raise HTTPException(404, "No such line of business.")
    if db.scalar(select(func.count(Application.id)).where(Application.lob_id == lid)):
        raise HTTPException(409, "Move its applications to another line of business first.")
    db.delete(x)
    store.log(db, me.email, "lob.delete", x.name)
    seclog.record(db, "delete.lob", me.email, detail=x.name)
    db.commit()
    return {"ok": True}


@router.post("/lobs/import")
async def import_lobs(text: Optional[str] = Form(None), file: Optional[UploadFile] = File(None),
                      db: Session = Depends(get_db), me: User = Depends(can_edit)):
    tables = await _tables(file, text)
    names = [r[0] for _, rows in tables[:1] for r in rows if r]
    res = importer.import_lobs(db, names)
    store.log(db, me.email, "lob.import", f"{len(res['created_lobs'])} added")
    db.commit()
    return res


# ---------------------------------------------------------------- applications
class AppIn(BaseModel):
    name: str
    project_id: str = ""
    lob_id: Optional[int] = None
    team: str = ""
    respondent_name: str = ""
    respondent_email: str = ""


class AppPatch(BaseModel):
    name: Optional[str] = None
    project_id: Optional[str] = None
    lob_id: Optional[int] = None
    team: Optional[str] = None
    respondent_name: Optional[str] = None
    respondent_email: Optional[str] = None


def _apps(db: Session):
    return db.scalars(select(Application).order_by(func.lower(Application.name), Application.id)).all()


@router.get("/applications")
def list_apps(db: Session = Depends(get_db), _: User = Depends(can_view)):
    return [app_out(a) for a in _apps(db)]


@router.post("/applications")
def add_app(body: AppIn, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    if not body.name.strip():
        raise HTTPException(422, "Enter the application name.")
    if body.lob_id is not None and not db.get(Lob, body.lob_id):
        raise HTTPException(422, "Choose a line of business from the list.")
    a = Application(**{k: (one_line(v)[:254] if isinstance(v, str) else v) for k, v in body.model_dump().items()})
    db.add(a)
    store.log(db, me.email, "app.add", a.name)
    db.commit()
    return app_out(a)


@router.patch("/applications/{aid}")
def update_app(aid: int, body: AppPatch, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    a = db.get(Application, aid)
    if not a:
        raise HTTPException(404, "No such application.")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and not (data["name"] or "").strip():
        raise HTTPException(422, "The application needs a name.")
    if data.get("lob_id") is not None and not db.get(Lob, data["lob_id"]):
        raise HTTPException(422, "Choose a line of business from the list.")
    for k, v in data.items():
        setattr(a, k, one_line(v)[:254] if isinstance(v, str) else v)
    if "respondent_email" in data:
        store.log(db, me.email, "app.respondent", f"{a.name}: {a.respondent_email or '(none)'}")
        seclog.record(db, "respondent.change", me.email, detail=f"{a.name}: {a.respondent_email or '(none)'}")
    db.commit()
    db.refresh(a)
    return app_out(a)


@router.delete("/applications/{aid}")
def delete_app(aid: int, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    a = db.get(Application, aid)
    if not a:
        raise HTTPException(404, "No such application.")
    store.log(db, me.email, "app.delete", f"{a.name}{' (with its survey response)' if a.invitation else ''}")
    seclog.record(db, "delete.application", me.email, detail=f"{a.name}{' (with its survey response)' if a.invitation else ''}")
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.post("/applications/import")
async def import_apps(mode: str = Form("add"), text: Optional[str] = Form(None), file: Optional[UploadFile] = File(None),
                      db: Session = Depends(get_db), me: User = Depends(can_edit)):
    tables = await _tables(file, text)
    try:
        res = importer.import_applications(db, tables, "replace" if mode == "replace" else "add")
    except importer.ImportProblem as exc:
        raise HTTPException(422, str(exc)) from exc
    store.log(db, me.email, "app.import", f"{res['added']} added, {res['updated']} updated ({mode})")
    if mode == "replace":
        seclog.record(db, "delete.applications", me.email, detail="Replaced all applications by import")
    db.commit()
    return res


# ---------------------------------------------------------------- questions
class QuestionPatch(BaseModel):
    text: Optional[str] = None
    help: Optional[str] = None
    required: Optional[bool] = None
    core: Optional[bool] = None
    show_if: Optional[str] = None
    options: Optional[list[str]] = None


@router.get("/questions")
def list_questions(db: Session = Depends(get_db), _: User = Depends(can_view)):
    return [q_out(q) for q in db.scalars(select(Question).order_by(Question.position, Question.id))]


@router.patch("/questions/{qid}")
def update_question(qid: int, body: QuestionPatch, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(404, "No such question.")
    data = body.model_dump(exclude_unset=True)
    if "text" in data and not (data["text"] or "").strip():
        raise HTTPException(422, "The question needs some text.")
    if "options" in data:
        data["options"] = [o.strip() for o in data["options"] if o and o.strip()]
    for k, v in data.items():
        setattr(q, k, v.strip() if isinstance(v, str) else v)
    store.log(db, me.email, "question.update", f"{q.qid}: {', '.join(data)}")
    db.commit()
    return q_out(q)


@router.post("/questions/import")
async def import_questions(mode: str = Form("replace"), text: Optional[str] = Form(None),
                           file: Optional[UploadFile] = File(None),
                           db: Session = Depends(get_db), me: User = Depends(can_edit)):
    tables = await _tables(file, text)
    try:
        res = importer.import_questions(db, tables, "add" if mode == "add" else "replace")
    except importer.ImportProblem as exc:
        raise HTTPException(422, str(exc)) from exc
    store.log(db, me.email, "question.import", f"{res['imported']} questions ({mode})")
    if mode != "add":
        seclog.record(db, "delete.questions", me.email, detail="Replaced the question bank by import")
    db.commit()
    return res


@router.get("/templates/{kind}.xlsx")
def template(kind: str, _: User = Depends(can_view)):
    if kind not in ("applications", "questions"):
        raise HTTPException(404, "No such template.")
    data = export.template(kind)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="QE_Connect_{kind}_template.xlsx"'})


def lob_names(db: Session) -> list[str]:
    return [x.name for x in db.scalars(select(Lob).order_by(Lob.position, Lob.id))]


@router.get("/survey-preview")
def survey_preview(db: Session = Depends(get_db), _: User = Depends(can_view)):
    """The survey exactly as respondents get it, for the Preview button."""
    lobs = lob_names(db)
    qs = db.scalars(select(Question).order_by(Question.position, Question.id)).all()
    return {"questions": [{**q_out(q), "options": rules.options_for(q, lobs)} for q in qs]}


__all__ = ["router", "app_out", "q_out", "lob_names", "email_ok"]

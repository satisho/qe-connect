"""One-click sample data for demos, and whole-workspace backup (JSON export / import)."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Activity, Application, Email, Invitation, Lob, Question, Setting, utcnow
from . import mail, store

LOBS = ["Customer Journey & Revenue Management", "Asset Management & Fleet Reliability"]
APPS = [
    ("eBooking", "PRJ-1042", 0, "ART#1 Digital Customer Experience", "Jordan Lee", "jordan.lee@example.com"),
    ("Mobile app (iOS / Android)", "PRJ-1107", 0, "ART#1 Digital Customer Experience", "Priya Shah", "priya.shah@example.com"),
    ("Terminal POS", "PRJ-0870", 0, "ART#2 Terminal & Onboard", "Marc Tremblay", "marc.tremblay@example.com"),
    ("Contact centre CRM", "", 0, "ART#2 Terminal & Onboard", "Aisha Khan", "aisha.khan@example.com"),
    ("Maximo 9", "PRJ-0915", 1, "ART#3 Fleet & Asset Systems", "Daniel Wu", "daniel.wu@example.com"),
    ("Vessel maintenance mobile", "PRJ-1121", 1, "ART#3 Fleet & Asset Systems", "Sofia Martins", "sofia.martins@example.com"),
    ("Fuel monitoring (OT)", "", 1, "Fleet Engineering", "", ""),
]
A = "A. About You & the Application"
B = "B. Application Profile"
L = "L. Planning, Governance & Capacity"
M = "M. Shift-Left & Quality by Design"
CTX = "Context (not scored)"
RAP = "Respondent & application profile"
VENDOR_RULE = ("Show if B2 is 'Packaged software (COTS) hosted by BC Ferries' or 'SaaS / vendor-hosted cloud platform' "
               "or 'Custom-built by a vendor' or 'Package with custom extensions (hybrid)'")
# qid, section, pillar, focus, text, help, type, options, required, core, show_if
QUESTIONS = [
    ("A1", A, CTX, RAP, "Your name, role/title and email.", "Used only to follow up on your answers.", "short", "", 1, 1, ""),
    ("A2", A, CTX, RAP, "Which Line of Business (LOB) does the application you are describing belong to?", "Please submit one response per application.", "single", "", 1, 1, "Options mirror the LOBs on the 'Lists' tab"),
    ("A3", A, CTX, RAP, "Application or project name (and Project ID, if there is one).", "e.g. eBooking, Terminal POS, Maximo 9.", "short", "", 1, 1, ""),
    ("A4", A, CTX, RAP, "Which Agile Release Train (ART), POD or delivery team looks after this application?", 'e.g. ART#1 Digital Customer Experience. Write "Not sure" if unknown.', "short", "", 1, 1, ""),
    ("B1", B, CTX, RAP, "In one or two sentences, what does this application do and who uses it?", "", "long", "", 1, 1, ""),
    ("B2", B, CTX, RAP, "What type of application is it?", "", "single", "Packaged software (COTS) hosted by BC Ferries\nSaaS / vendor-hosted cloud platform\nCustom-built by BC Ferries team\nCustom-built by a vendor\nPackage with custom extensions (hybrid)\nLegacy / nearing end of life\nOther (please specify)", 1, 1, ""),
    ("B3", B, CTX, RAP, "What is the main technology or platform?", "e.g. SAP Hybris, IBM Maximo, Oracle EBS, iOS/Android, .NET", "short", "", 1, 1, ""),
    ("B4", B, "QE Engineering", "Customer Journey & Business Validation", "Through which channels or interfaces is it used? (Select all that apply)", "", "multi", "Public website\nMobile app - iOS\nMobile app - Android\nTerminal kiosk / point of sale\nVessel system / point of sale\nInternal desktop or web application\nBack-office / batch processing\nOperational technology (OT) / sensors\nAPIs / integrations only\nOther (please specify)", 1, 1, ""),
    ("B5", B, "Quality Governance", "Quality Risk, Assurance & Compliance", "How business-critical is this application?", "", "single", "Safety-critical\nRevenue-critical\nOperations-critical\nImportant, but workarounds exist\nLow impact\nNot sure", 1, 1, ""),
    ("B6", B, "QE Engineering", "Performance & Reliability Engineering", "Roughly how many people use it, and are there seasonal peaks (e.g. summer sailings)?", 'A rough answer is fine, e.g. "300 staff; public traffic peaks Jul-Aug".', "short", "", 0, 0, ""),
    ("B7", B, "QE Delivery Management", "Quality Planning & Forecasting", "What lifecycle stage is the application in?", "", "single", "Planned - not started\nIn build / implementation\nIn production - actively enhanced\nIn production - maintenance only\nPlanned for replacement or retirement", 1, 1, ""),
    ("B8", B, "QE Engineering", "End-to-End, API & Integration Quality", "Approximately how many other systems does it integrate with?", "", "single", "None\n1-3\n4-10\n11-25\nMore than 25\nNot known", 1, 1, ""),
    ("B9", B, "QE Engineering", "End-to-End, API & Integration Quality", "List the key upstream and downstream systems.", "e.g. Maximo <-> Oracle EBS", "long", "", 0, 0, "Show if B8 is not 'None' or 'Not known'"),
    ("L8", L, "Quality Governance", "Portfolio, Partner & Value Governance", "Is testing evidence from vendors reviewed and accepted by BC Ferries before sign-off?", "", "single", "Always - formal review\nSometimes\nRarely\nNot applicable (no vendor testing)\nNot sure", 0, 0, VENDOR_RULE),
    ("L9", L, "QE Talent & Enablement", "Talent Ratio - Developer : Tester", "How many developers work on this application (approximate)?", "Used with the tester count to work out the developer-to-tester ratio.", "number", "", 1, 1, ""),
    ("L10", L, "QE Talent & Enablement", "Capability Intelligence & Gap Analysis", "Does each module or area have a trained backup tester?", "", "single", "Yes - all areas\nSome areas\nNo - single owners\nNot sure", 0, 0, ""),
    ("L11", L, "QE Talent & Enablement", "Continuous Learning & Enablement", "Is there an onboarding process for new team members, and is learning time built into planning?", "", "single", "Yes - both\nOnboarding exists, learning time not planned\nInformal\nNone\nNot sure", 0, 0, ""),
    ("L12", L, "QE Talent & Enablement", "Knowledge, Assets & InnerSource", "Where are reusable test assets and good practices kept, and can other teams find them?", "", "single", "Central repository others can search\nTeam-level repository only\nIndividuals' files / spreadsheets\nNot kept\nNot sure", 0, 0, ""),
    ("L13", L, "QE Talent & Enablement", "Knowledge, Assets & InnerSource", "Are retrospectives or Inspect & Adapt workshops held, and are quality improvement actions tracked to closure?", "", "single", "Yes - actions tracked to closure\nHeld, actions not tracked\nRarely held\nNot held\nNot sure", 0, 0, ""),
    ("M1", M, "QE Engineering", "Testability & Quality-by-Design", "When are test cases or acceptance tests usually written?", "", "single", "Before development starts (e.g. BDD / ATDD)\nWhile the story is being developed\nAfter development, in the same iteration\nIn a later iteration\nNot sure", 1, 1, ""),
    ("M2", M, "Future-Ready QE", "Continuous Quality Engineering", "When is testing of a story usually completed?", "", "single", "Within the same iteration\nIn the next iteration\nIn the end-of-PI / IP iteration\nIn a later system-test phase\nVaries widely\nNot sure", 1, 1, ""),
    ("M3", M, "QE Engineering", "Testability & Quality-by-Design", "Which test levels are normally completed inside the iteration? (Select all that apply)", "", "multi", "Unit\nStory / component\nFeature / system\nCross-team integration\nUAT\nData migration\nCutover rehearsal\nNone of these", 1, 1, ""),
]
EBOOKING = {
    "B1": "Lets customers book and change sailings, buy passenger and vehicle fares, and manage reservations. Used by the public and contact-centre agents.",
    "B2": "Custom-built by a vendor", "B3": "SAP Hybris, iOS/Android",
    "B4": ["Public website", "Mobile app - iOS", "Mobile app - Android", "APIs / integrations only"],
    "B5": "Revenue-critical", "B6": "About 2M bookings a year; peaks Jun-Sep and long weekends",
    "B7": "In production - actively enhanced", "B8": "4-10",
    "B9": "Payment gateway, SAP ERP, Terminal POS, loyalty platform, sailing schedule service",
    "L8": "Sometimes", "L9": "14", "L10": "Some areas", "L11": "Onboarding exists, learning time not planned",
    "L12": "Team-level repository only", "L13": "Held, actions not tracked",
    "M1": "While the story is being developed", "M2": "In the next iteration", "M3": ["Unit", "Story / component"],
}
MAXIMO = {
    "B1": "Plans and tracks maintenance work orders for the fleet and terminals. Used by fleet engineers, planners and stores staff.",
    "B2": "Packaged software (COTS) hosted by BC Ferries", "B3": "IBM Maximo",
    "B4": ["Internal desktop or web application", "Mobile app - Android", "Back-office / batch processing"],
    "B5": "Safety-critical", "B7": "In production - actively enhanced", "B8": "4-10", "L9": "6",
    "M1": "After development, in the same iteration", "M2": "In a later system-test phase", "M3": ["Unit", "Feature / system"],
}


def new_reference() -> str:
    return "QEA-" + "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(8))


def question_rows() -> list[dict]:
    return [dict(qid=q[0], section=q[1], pillar=q[2], focus=q[3], text=q[4], help=q[5], rtype=q[6],
                 options=[o for o in q[7].split("\n") if o], required=bool(q[8]), core=bool(q[9]), show_if=q[10],
                 position=i) for i, q in enumerate(QUESTIONS, start=1)]


def prefill(app: Application, qs) -> tuple[dict, dict]:
    a: dict = {}
    o: dict = {}
    lob = app.lob.name if app.lob else ""
    for q in qs:
        t = q.text.lower()
        if "your name" in t:
            a[q.qid] = ", ".join(x for x in (app.respondent_name, app.respondent_email) if x)
        elif "line of business" in t and lob:
            a[q.qid] = lob
        elif "application or project name" in t:
            a[q.qid] = app.name + (f" ({app.project_id})" if app.project_id else "")
        elif ("release train" in t or "delivery team" in t) and app.team:
            a[q.qid] = app.team
    return a, o


def clear_survey_data(db: Session) -> None:
    for model in (Email, Invitation, Application, Question, Lob):
        db.execute(delete(model))
    db.flush()


def load(db: Session, actor: str) -> None:
    clear_survey_data(db)
    lobs = [Lob(name=n, position=i) for i, n in enumerate(LOBS, start=1)]
    db.add_all(lobs)
    db.flush()
    qs = [Question(**r) for r in question_rows()]
    db.add_all(qs)
    apps = []
    for name, pid, li, team, rn, re_ in APPS:
        a = Application(name=name, project_id=pid, lob_id=lobs[li].id, team=team, respondent_name=rn, respondent_email=re_)
        db.add(a)
        apps.append(a)
    db.flush()
    for a in apps:
        db.refresh(a)
    now = utcnow()

    def invite(a: Application, status: str, days_ago: float, mode="core", answers=None, opened=None, completed=None):
        inv = Invitation(application_id=a.id, token=secrets.token_urlsafe(18), status=status, mode=mode,
                         due_at=now + timedelta(days=12), sent_at=now - timedelta(days=days_ago),
                         opened_at=now - timedelta(days=opened) if opened is not None else None,
                         completed_at=now - timedelta(days=completed) if completed is not None else None,
                         answers={}, other={}, prefilled=[], reference=new_reference())
        if opened is not None:
            pre, oth = prefill(a, qs)
            inv.answers = {**pre, **(answers or {})}
            inv.prefilled = list(pre)
            inv.started_at = inv.opened_at if answers else None
        db.add(inv)
        db.flush()
        a.invitation = inv
        e = mail.compose(db, a, inv, "Invitation", actor)
        e.status, e.via, e.created_at, e.sent_at = "recorded", "sim", inv.sent_at, inv.sent_at
        return inv

    invite(apps[0], "completed", 6, "all", EBOOKING, opened=5.2, completed=4.9)
    invite(apps[4], "completed", 6, "core", MAXIMO, opened=3, completed=2.8)
    invite(apps[2], "progress", 6, "core", {"B1": "Sells tickets and onboard items at terminals and on vessels.",
                                            "B2": "Package with custom extensions (hybrid)", "B3": ".NET, Windows POS"}, opened=1.5)
    invite(apps[1], "opened", 3, opened=0.4)
    invite(apps[3], "sent", 3)
    store.log(db, actor, "sample.load", "Loaded sample LOBs, applications, questions and responses")
    db.commit()


# ---------------------------------------------------------------- workspace backup
def _iso(dt: datetime | None):
    return dt.isoformat() if dt else None


def _dt(s):
    return datetime.fromisoformat(s) if s else None


def export_workspace(db: Session) -> dict:
    lobs = db.scalars(select(Lob).order_by(Lob.position)).all()
    return {
        "format": "qe-connect-workspace", "version": 1, "exported_at": utcnow().isoformat(),
        "settings": {s.key: s.value for s in db.scalars(select(Setting))},
        "lobs": [{"id": x.id, "name": x.name, "position": x.position} for x in lobs],
        "questions": [{k: getattr(q, k) for k in ("qid", "position", "section", "pillar", "focus", "text", "help", "rtype",
                                                    "options", "required", "core", "show_if", "source", "dimension")}
                      for q in db.scalars(select(Question).order_by(Question.position))],
        "applications": [{
            "id": a.id, "name": a.name, "project_id": a.project_id, "lob_id": a.lob_id, "team": a.team,
            "respondent_name": a.respondent_name, "respondent_email": a.respondent_email,
            "invitation": None if not a.invitation else {
                k: (_iso(v) if isinstance(v, datetime) else v) for k, v in {
                    "token": a.invitation.token, "status": a.invitation.status, "mode": a.invitation.mode,
                    "due_at": a.invitation.due_at, "sent_at": a.invitation.sent_at, "opened_at": a.invitation.opened_at,
                    "started_at": a.invitation.started_at, "completed_at": a.invitation.completed_at,
                    "answers": a.invitation.answers, "other": a.invitation.other, "prefilled": a.invitation.prefilled,
                    "reminders": a.invitation.reminders, "reference": a.invitation.reference}.items()}}
            for a in db.scalars(select(Application).order_by(Application.id))],
        "emails": [{k: (_iso(getattr(e, k)) if isinstance(getattr(e, k), datetime) else getattr(e, k)) for k in (
            "application_id", "kind", "to_addr", "to_name", "from_addr", "subject", "body", "status", "via", "error",
            "attempts", "created_at", "sent_at", "created_by")} for e in db.scalars(select(Email).order_by(Email.id))],
    }


def import_workspace(db: Session, data: dict, actor: str) -> dict:
    if not isinstance(data, dict) or data.get("format") != "qe-connect-workspace":
        raise ValueError("This isn't a QE Connect workspace file.")
    clear_survey_data(db)
    db.execute(delete(Setting))
    for k, v in (data.get("settings") or {}).items():
        if k == "delivery" and isinstance(v, dict):
            v = {**v, "tested": None}
        db.add(Setting(key=k, value=v))
    lob_map = {}
    for x in data.get("lobs", []):
        lob = Lob(name=x["name"], position=x.get("position", 0))
        db.add(lob)
        db.flush()
        lob_map[x["id"]] = lob.id
    for q in data.get("questions", []):
        db.add(Question(**q))
    app_map = {}
    for a in data.get("applications", []):
        inv = a.pop("invitation", None)
        old_id = a.pop("id")
        a["lob_id"] = lob_map.get(a.get("lob_id"))
        app = Application(**a)
        db.add(app)
        db.flush()
        app_map[old_id] = app.id
        if inv:
            for k in ("due_at", "sent_at", "opened_at", "started_at", "completed_at"):
                inv[k] = _dt(inv.get(k))
            inv.setdefault("reference", "")
            inv["reference"] = inv["reference"] or new_reference()
            db.add(Invitation(application_id=app.id, **inv))
    for e in data.get("emails", []):
        e["application_id"] = app_map.get(e.get("application_id"))
        for k in ("created_at", "sent_at"):
            e[k] = _dt(e.get(k))
        if e.get("status") == "queued":
            e["status"] = "failed"
            e["error"] = "Not sent before the backup was made."
        db.add(Email(**e))
    store.log(db, actor, "workspace.import", f"Restored {len(app_map)} applications from a backup")
    db.commit()
    return {"applications": len(app_map), "questions": len(data.get("questions", []))}

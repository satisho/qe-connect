"""Response downloads (CSV and Excel) and whole-workspace backup files."""
from __future__ import annotations

import csv
import io
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Application, Question
from . import rules

LONG_HEADER = ["Application", "Project ID", "Line of business", "Delivery team", "Respondent", "Respondent email",
               "Completed", "Survey length", "Q ID", "Section", "Pillar", "Focus area", "Question", "Answer"]


def safe(v) -> str:
    """Stop spreadsheet formula injection from free-text answers."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _when(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else ""


def questions(db: Session) -> list[Question]:
    return list(db.scalars(select(Question).order_by(Question.position, Question.id)))


def long_rows(app: Application, qs: list[Question]) -> list[list[str]]:
    inv = app.invitation
    known = {q.qid for q in qs}
    rows = []
    for q in qs:
        ans = rules.format_answer(q, inv.answers or {}, inv.other or {})
        asked = (inv.mode == "all" or q.core) and rules.shows(q, inv.answers or {}, known)
        if not asked and not ans:
            ans = "(not asked)"
        rows.append([app.name, app.project_id, app.lob.name if app.lob else "", app.team, app.respondent_name,
                     app.respondent_email, _when(inv.completed_at), "Full" if inv.mode == "all" else "Core",
                     q.qid, q.section, q.pillar, q.focus, q.text, ans])
    return rows


def to_csv(rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    for r in rows:
        w.writerow([safe(c) for c in r])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_xlsx(sheets: list[tuple[str, list[list]]], widths: dict[str, list[int]] | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets:
        ws = wb.create_sheet(name[:31])
        for r in rows:
            ws.append([safe(c) for c in r])
        if rows:
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="0A5A8A")
                c.alignment = Alignment(vertical="top", wrap_text=True)
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
        for i, wdt in enumerate((widths or {}).get(name, []), start=1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = wdt
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(vertical="top", wrap_text=True)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


LONG_WIDTHS = [24, 12, 26, 22, 20, 28, 18, 10, 7, 26, 20, 26, 50, 40]


def one_response(app: Application, qs: list[Question], fmt: str) -> bytes:
    rows = [LONG_HEADER, *long_rows(app, qs)]
    if fmt == "csv":
        return to_csv(rows)
    return to_xlsx([("Response", rows)], {"Response": LONG_WIDTHS})


def all_responses(apps: list[Application], qs: list[Question], fmt: str) -> bytes:
    long = [LONG_HEADER]
    for a in apps:
        long += long_rows(a, qs)
    if fmt == "csv":
        return to_csv(long)
    wide = [["Application", "Project ID", "Line of business", "Respondent", "Completed", "Survey length",
             *[f"{q.qid} {q.text}" for q in qs]]]
    for a in apps:
        inv = a.invitation
        wide.append([a.name, a.project_id, a.lob.name if a.lob else "", a.respondent_name, _when(inv.completed_at),
                     "Full" if inv.mode == "all" else "Core",
                     *[rules.format_answer(q, inv.answers or {}, inv.other or {}) for q in qs]])
    return to_xlsx([("Summary", wide), ("Answers", long)],
                   {"Summary": [24, 12, 26, 20, 18, 10] + [28] * len(qs), "Answers": LONG_WIDTHS})


def template(kind: str) -> bytes:
    if kind == "applications":
        rows = [["Application", "Project ID", "Line of Business", "Delivery team / ART", "Respondent name", "Respondent email"],
                ["Customer portal", "PRJ-1042", "Customer & Digital Channels", "ART#1 Digital Customer Experience",
                 "Jordan Lee", "jordan.lee@example.com"]]
        return to_xlsx([("Applications", rows)], {"Applications": [26, 12, 34, 30, 20, 30]})
    rows = [["Q ID", "Section", "Pillar", "Focus area", "Question (as shown to respondent)", "Help text",
             "Response type", "Answer options (one per line)", "Required?", "Priority", "Show-if logic", "Source",
             "EQA dimension"],
            ["B8", "B. Application Profile", "QE Engineering", "End-to-End, API & Integration Quality",
             "Approximately how many other systems does it integrate with?", "", "Single choice",
             "None\n1-3\n4-10\n11-25\nMore than 25\nNot known", "Yes", "Core", "", "", "Scoping"],
            ["B9", "B. Application Profile", "QE Engineering", "End-to-End, API & Integration Quality",
             "List the key upstream and downstream systems.", "e.g. CRM <-> ERP", "Long text", "", "No",
             "Optional", "Show if B8 is not 'None' or 'Not known'", "", "Scoping"]]
    return to_xlsx([("Survey Questions", rows), ("Lists", [["Line of Business"], ["Customer & Digital Channels"],
                                                           ["Operations & Enterprise Systems"]])],
                   {"Survey Questions": [7, 26, 20, 26, 50, 30, 15, 34, 10, 10, 34, 20, 14], "Lists": [40]})

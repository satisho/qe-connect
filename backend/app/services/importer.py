"""Importing applications, questions and lines of business from Excel, CSV or pasted cells."""
from __future__ import annotations

import csv
import io
import re
from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import Application, Lob, Question
from . import rules
from .mail import email_ok, one_line

APP_SPEC = {
    "respondent_email": ["respondentemail", "respondentemailaddress", "emailaddress", "email"],
    "respondent_name": ["respondentname", "respondent", "contactname", "name"],
    "project_id": ["projectid", "project"],
    "lob": ["lineofbusiness", "lob"],
    "team": ["deliveryteamart", "deliveryteam", "art", "team", "pod"],
    "name": ["application", "applicationname", "app", "applicationorproject"],
}
Q_SPEC = {
    "qid": ["qid", "questionid", "id"],
    "text": ["questionasshowntorespondent", "questiontext", "question"],
    "help": ["helptextshownunderthequestion", "helptext", "help"],
    "rtype": ["responsetype", "type"],
    "options": ["answeroptionsoneperline", "answeroptions", "options"],
    "required": ["required"],
    "core": ["priority"],
    "show_if": ["showiflogic", "showif", "logic"],
    "source": ["assessmentchecklistsource", "source"],
    "dimension": ["eqadimension", "dimension"],
    "section": ["section"],
    "pillar": ["pillar"],
    "focus": ["focusarea", "focus"],
}
TYPE_MAP = {"shorttext": "short", "text": "short", "longtext": "long", "paragraph": "long", "singlechoice": "single",
            "single": "single", "dropdown": "single", "multiplechoice": "multi", "multichoice": "multi",
            "multiselect": "multi", "checkbox": "multi", "number": "number", "numeric": "number"}
MAX_ROWS = 5000
MAX_UNZIPPED = 100 * 1024 * 1024   # total uncompressed size of a workbook
MAX_MEMBERS = 2000                 # files inside the workbook
MAX_SHEETS = 60
MAX_RATIO = 200                    # compression ratio that suggests a "zip bomb"


def check_workbook(data: bytes) -> None:
    """Refuse workbooks that would take too much memory before any XML is parsed."""
    import zipfile

    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ImportProblem("This file could not be opened as an Excel workbook.") from exc
    infos = z.infolist()
    total = sum(i.file_size for i in infos)
    sheets = sum(1 for i in infos if i.filename.startswith("xl/worksheets/") and i.filename.endswith(".xml"))
    if len(infos) > MAX_MEMBERS or sheets > MAX_SHEETS:
        raise ImportProblem(f"This workbook has too many parts or sheets (limit {MAX_SHEETS} sheets).")
    if total > MAX_UNZIPPED or any(i.compress_size and i.file_size / i.compress_size > MAX_RATIO and i.file_size > 5_000_000 for i in infos):
        raise ImportProblem("This workbook is too large once unpacked. Remove unused sheets or save it again in Excel.")


class ImportProblem(Exception):
    pass


def norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def map_columns(header: list, spec: dict) -> dict[str, int]:
    h = [norm(x) for x in header]
    used: set[int] = set()
    out: dict[str, int] = {}
    for exact in (True, False):
        for field, keys in spec.items():
            if field in out:
                continue
            for k in keys:
                idx = next((i for i, x in enumerate(h) if i not in used and x and (x == k if exact else x.startswith(k))), -1)
                if idx >= 0:
                    out[field] = idx
                    used.add(idx)
                    break
    return out


def parse_text(text: str) -> list[list[str]]:
    text = text.lstrip("﻿")
    first = text.splitlines()[0] if text.strip() else ""
    delim = "\t" if "\t" in first else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    return [r for r in rows if any(str(c).strip() for c in r)]


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def read_tables(filename: str, data: bytes) -> list[tuple[str, list[list[str]]]]:
    """Return (sheet name, rows) for an uploaded .xlsx, .csv/.tsv/.txt file."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        check_workbook(data)
        from openpyxl.xml import DEFUSEDXML

        if not DEFUSEDXML:  # pragma: no cover - guarded by requirements.txt
            raise ImportProblem("The server is missing the defusedxml package. Run the start script again.")
        try:
            from openpyxl import load_workbook

            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:
            raise ImportProblem("This file could not be opened as an Excel workbook.") from exc
        out = []
        for ws in wb.worksheets:
            rows = []
            for r in ws.iter_rows(values_only=True):
                cells = [_cell(c) for c in r]
                if any(cells):
                    rows.append(cells)
                if len(rows) > MAX_ROWS:
                    break
            out.append((ws.title, rows))
        wb.close()
        return out
    if name.endswith(".xls"):
        raise ImportProblem("Old .xls files aren't supported. Save the workbook as .xlsx and try again.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    return [(filename or "pasted", parse_text(text))]


def find_header(rows: list[list[str]], spec: dict, need: Iterable[str]) -> tuple[int, dict[str, int]] | None:
    for i, r in enumerate(rows[:15]):
        m = map_columns(r, spec)
        if all(k in m for k in need):
            return i, m
    return None


def _lob_id(db: Session, name: str, created: list[str]) -> int | None:
    name = name.strip()
    if not name:
        return None
    lob = db.scalar(select(Lob).where(func.lower(Lob.name) == name.lower()))
    if not lob:
        pos = (db.scalar(select(func.max(Lob.position))) or 0) + 1
        lob = Lob(name=name, position=pos)
        db.add(lob)
        db.flush()
        created.append(name)
    return lob.id


def import_applications(db: Session, tables, mode: str) -> dict:
    warnings: list[str] = []
    created_lobs: list[str] = []
    found = None
    for sheet, rows in tables:
        hit = find_header(rows, APP_SPEC, ["name"])
        if hit:
            found = (sheet, rows, *hit)
            break
    if not found:
        raise ImportProblem('No "Application" column found. Include the header row: Application, Project ID, '
                            "Line of Business, Delivery team / ART, Respondent name, Respondent email.")
    sheet, rows, hi, cols = found
    parsed = []
    for n, r in enumerate(rows[hi + 1:], start=hi + 2):
        g = lambda k: (r[cols[k]] if k in cols and cols[k] < len(r) else "").strip()  # noqa: E731
        if not g("name"):
            if any(c.strip() for c in r):
                warnings.append(f"Row {n}: no application name, skipped.")
            continue
        parsed.append({k: one_line(g(k))[:254] for k in APP_SPEC})
    if mode == "replace":
        db.execute(delete(Application))
    added = updated = 0
    for p in parsed:
        email = p["respondent_email"]
        if email and not email_ok(email):
            warnings.append(f'{p["name"]}: "{email}" doesn\'t look like an email address.')
        elif not email:
            warnings.append(f'{p["name"]}: no respondent email yet.')
        lob_id = _lob_id(db, p["lob"], created_lobs)
        existing = None
        if mode != "replace":
            existing = db.scalar(select(Application).where(func.lower(Application.name) == p["name"].lower(),
                                                           Application.project_id == p["project_id"]))
        app = existing or Application(name=p["name"])
        app.project_id, app.lob_id, app.team = p["project_id"], lob_id, p["team"]
        app.respondent_name, app.respondent_email = p["respondent_name"], email
        if existing:
            updated += 1
        else:
            db.add(app)
            added += 1
    return {"added": added, "updated": updated, "created_lobs": created_lobs, "warnings": warnings[:100], "sheet": sheet}


def _q_from(r: list[str], cols: dict, pos: int) -> dict:
    g = lambda k: (r[cols[k]] if k in cols and cols[k] < len(r) else "").strip()  # noqa: E731
    return {
        "qid": one_line(g("qid")).upper()[:20], "text": g("text"), "help": g("help"),
        "section": one_line(g("section"))[:200] or "General", "pillar": one_line(g("pillar"))[:200], "focus": one_line(g("focus"))[:200], "rtype": TYPE_MAP.get(norm(g("rtype")), "short"),
        "options": [o.strip() for o in re.split(r"\r?\n", g("options")) if o.strip()],
        "required": norm(g("required")).startswith("y"),
        "core": not norm(g("core")).startswith("opt"),
        "show_if": g("show_if"), "source": g("source"), "dimension": g("dimension"), "position": pos,
    }


def import_questions(db: Session, tables, mode: str) -> dict:
    warnings: list[str] = []
    qs: list[dict] = []
    sheets_used = []
    lobs_found: list[str] = []
    for sheet, rows in tables:
        hit = find_header(rows, Q_SPEC, ["qid", "text"])
        if hit:
            hi, cols = hit
            n0 = len(qs)
            for r in rows[hi + 1:]:
                q = _q_from(r, cols, len(qs) + 1)
                if q["qid"] and q["text"]:
                    qs.append(q)
            if len(qs) > n0:
                sheets_used.append(f"{sheet} ({len(qs) - n0})")
            continue
        # a "Lists" sheet: pick up the LOB column
        for i, r in enumerate(rows[:10]):
            idx = next((j for j, c in enumerate(r) if norm(c) in ("lob", "lobs", "lineofbusiness", "linesofbusiness")), -1)
            if idx >= 0:
                lobs_found += [x[idx].strip() for x in rows[i + 1:] if idx < len(x) and x[idx].strip()]
                break
    if not qs:
        raise ImportProblem('No questions found. The sheet needs a header row with at least "Q ID" and '
                            '"Question" columns.')
    seen: dict[str, dict] = {}
    for q in qs:
        if q["qid"] in seen:
            warnings.append(f'{q["qid"]} appears more than once; the last one was kept.')
        seen[q["qid"]] = q
    final = list(seen.values())
    known = set(seen) | ({q.qid for q in db.scalars(select(Question))} if mode != "replace" else set())
    for q in final:
        r = rules.parse_rule(q["show_if"])
        if q["rtype"] in ("single", "multi") and not q["options"] and not (r and r.kind == "lobs"):
            warnings.append(f'{q["qid"]} is a choice question with no answer options.')
        if r and r.kind == "bad":
            warnings.append(f'{q["qid"]}: show-if rule not recognised, so it is always shown ("{q["show_if"][:120]}").')
        if r and r.kind == "match" and r.qid not in known:
            warnings.append(f"{q['qid']}: rule refers to {r.qid}, which isn't in the question bank.")
    if mode == "replace":
        db.execute(delete(Question))
        db.flush()
        for q in final:
            db.add(Question(**q))
    else:
        base = db.scalar(select(func.max(Question.position))) or 0
        for i, q in enumerate(final, start=1):
            row = db.scalar(select(Question).where(Question.qid == q["qid"]))
            if row:
                for k, v in q.items():
                    if k != "position":
                        setattr(row, k, v)
            else:
                q["position"] = base + i
                db.add(Question(**q))
    created_lobs: list[str] = []
    for name in dict.fromkeys(lobs_found):
        _lob_id(db, name, created_lobs)
    return {"imported": len(final), "sections": len({q["section"] for q in final}), "sheets": sheets_used,
            "created_lobs": created_lobs, "warnings": warnings[:100]}


def import_lobs(db: Session, names: list[str]) -> dict:
    created: list[str] = []
    for n in dict.fromkeys(x.strip() for x in names if x and x.strip()):
        if norm(n) in ("lob", "lineofbusiness", "linesofbusiness"):
            continue
        _lob_id(db, one_line(n)[:200], created)
    return {"created_lobs": created}

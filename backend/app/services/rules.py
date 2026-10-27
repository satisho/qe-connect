"""Show-if rules, visibility and answer checks for the survey.

Rules come from the question bank's "Show-if logic" column. Two forms are understood:

* ``Show if B8 is not 'None' or 'Not known'``  (also: is, includes, contains, =)
* a note that the options mirror the LOB list ("Options mirror the LOBs on the 'Lists' tab")

Anything else is kept as text and reported as "not recognised"; such a question is always shown.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

OTHER_RE = re.compile(r"^other\b", re.I)
NONE_RE = re.compile(r"^none of", re.I)
RULE_RE = re.compile(r"show\s+if\s+([A-Za-z]+\d+)\s+(is\s+not|isn't|not|is|equals|=|includes|contains)\s+(.+)", re.I)
QUOTED_RE = re.compile(r"'([^']+)'|\"([^\"]+)\"")


@dataclass(frozen=True)
class Rule:
    kind: str  # "lobs" | "match" | "bad"
    qid: str = ""
    negate: bool = False
    values: tuple = ()


def parse_rule(text: str | None) -> Optional[Rule]:
    if not text or not text.strip():
        return None
    t = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    if re.search(r"\blobs?\b", t, re.I) and re.search(r"mirror|lists", t, re.I):
        return Rule("lobs")
    m = RULE_RE.search(t)
    if not m:
        return Rule("bad")
    vals = [a or b for a, b in QUOTED_RE.findall(m.group(3))]
    if not vals:
        vals = [v.strip().rstrip(".") for v in re.split(r"\s+or\s+", m.group(3), flags=re.I) if v.strip()]
        # Unquoted values must be short answer labels; prose ("includes a vendor, system integrator ...") is not a rule.
        if not vals or any("," in v or len(v) > 40 for v in vals):
            return Rule("bad")
    return Rule("match", m.group(1).upper(), "not" in m.group(2).lower(), tuple(v.lower() for v in vals))


def is_other(v: Any) -> bool:
    return isinstance(v, str) and bool(OTHER_RE.match(v))


def options_for(q, lobs: list[str]) -> list[str]:
    r = parse_rule(q.show_if)
    if r and r.kind == "lobs":
        return [*lobs, "Other (please specify)"]
    return list(q.options or [])


def shows(q, answers: dict, known: set | None = None) -> bool:
    r = parse_rule(q.show_if)
    if not r or r.kind != "match":
        return True
    if known is not None and r.qid not in known:
        return True  # the rule points at a question that isn't in the bank: never hide it
    v = answers.get(r.qid)
    if v is None or v == "" or (isinstance(v, list) and not v):
        return False
    vals = [str(x).lower() for x in (v if isinstance(v, list) else [v])]
    hit = any(x in r.values for x in vals)
    return not hit if r.negate else hit


def visible(questions: Iterable, mode: str, answers: dict) -> list:
    questions = list(questions)
    known = {q.qid for q in questions}
    return [q for q in questions if (mode == "all" or q.core) and shows(q, answers, known)]


def answered(q, answers: dict, other: dict) -> bool:
    v = answers.get(q.qid)
    if v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not v):
        return False
    needs_other = any(is_other(x) for x in v) if isinstance(v, list) else is_other(v)
    if needs_other and not str(other.get(q.qid, "")).strip():
        return False
    return True


def problem(q, answers: dict, other: dict) -> Optional[str]:
    v = answers.get(q.qid)
    if q.rtype == "number" and v not in (None, ""):
        try:
            if float(v) < 0:
                raise ValueError
        except (TypeError, ValueError):
            return "Enter a whole number, e.g. 12."
    if not q.required:
        return None
    if not answered(q, answers, other):
        if v and (any(is_other(x) for x in v) if isinstance(v, list) else is_other(v)):
            return 'Tell us what "Other" means here.'
        return "Choose at least one option." if q.rtype == "multi" else "This question needs an answer."
    return None


def progress(questions: list, mode: str, answers: dict, other: dict) -> tuple[int, int]:
    vis = visible(questions, mode, answers)
    return sum(1 for q in vis if answered(q, answers, other)), len(vis)


def clean_answers(questions: list, lobs: list[str], answers: dict, other: dict) -> tuple[dict, dict]:
    """Keep only known questions and allowed values; trims long text."""
    byid = {q.qid: q for q in questions}
    out: dict = {}
    oth: dict = {}
    for k, v in (answers or {}).items():
        q = byid.get(k)
        if not q:
            continue
        if q.rtype in ("short", "long", "number"):
            if v is None:
                continue
            out[k] = str(v)[:5000]
        elif q.rtype == "single":
            if isinstance(v, str) and v in options_for(q, lobs):
                out[k] = v
        elif q.rtype == "multi":
            opts = options_for(q, lobs)
            if isinstance(v, list):
                picked = [o for o in opts if o in v]
                if any(NONE_RE.match(o) for o in picked):
                    picked = [o for o in picked if NONE_RE.match(o)][:1]
                out[k] = picked
    for k, v in (other or {}).items():
        if k in byid and isinstance(v, str):
            oth[k] = v[:1000]
    return out, oth


def format_answer(q, answers: dict, other: dict) -> str:
    v = answers.get(q.qid)
    if v is None or v == "" or v == []:
        return ""
    vals = v if isinstance(v, list) else [v]
    return "; ".join(f"Other: {other.get(q.qid, '')}" if is_other(x) else str(x) for x in vals)


def section_parts(section: str) -> tuple[str, str]:
    m = re.match(r"^([A-Z]{1,3})[.)]\s*(.*)$", section or "")
    return (m.group(1), m.group(2)) if m else ("", section or "General")

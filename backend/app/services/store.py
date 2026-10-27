"""Stored settings (survey name, invitation email, email delivery) and the activity feed."""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from ..models import Activity, Setting

DEFAULT_EMAIL = {
    "subject": "QE Connect: quality survey for {application}",
    "body": (
        "Hi {first_name},\n\n"
        "The QE Assessment team is building a picture of testing and quality practice across BC Ferries "
        "applications. You have been named as the contact for {application} ({lob}).\n\n"
        "Please complete the survey by {due_date}. It takes about 10 to 15 minutes and saves as you go, "
        "so you can stop and come back.\n\n"
        "Start the survey: {survey_link}\n\n"
        "There are no right or wrong answers, and \"Not sure\" is always fine. If someone else is better "
        "placed to answer, reply to this email and let us know.\n\n"
        "Thank you,\nQE Assessment team"
    ),
}

DEFAULT_DELIVERY = {
    "mode": "sim",  # sim | graph | smtp
    "tenant": "",
    "client": "",
    "auth_type": "secret",  # secret | cert
    "cert_thumbprint": "",
    "save_sent": True,
    "host": "",
    "port": 587,
    "security": "starttls",  # starttls | tls | none
    "smtp_auth": "none",  # none | login
    "username": "",
    "mailbox": "qe-connect@bcferries.com",
    "display_name": "QE Connect",
    "reply_to": "",
    "rate_per_minute": 30,
    "link_base": "",
    "tested": None,
}

DEFAULT_SECURITY = {"mfa_required": False, "idle_minutes": 30}

DEFAULTS: dict[str, Any] = {
    "security": DEFAULT_SECURITY,
    "campaign": {"name": "Application QA Survey · Wave 1", "default_due_days": 14},
    "email": DEFAULT_EMAIL,
    "delivery": DEFAULT_DELIVERY,
}


def get(db: Session, key: str) -> dict:
    row = db.get(Setting, key)
    base = copy.deepcopy(DEFAULTS.get(key, {}))
    if row and isinstance(row.value, dict):
        base.update(row.value)
    return base


def put(db: Session, key: str, value: dict) -> dict:
    merged = get(db, key)
    merged.update(value)
    row = db.get(Setting, key)
    if row:
        row.value = merged
    else:
        db.add(Setting(key=key, value=merged))
    return merged


def log(db: Session, actor: str, action: str, detail: str = "") -> None:
    db.add(Activity(actor=actor or "", action=action, detail=detail[:2000]))

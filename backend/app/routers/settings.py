"""Survey name, invitation email text and email delivery settings."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings as cfg
from ..db import get_db
from ..models import User
from ..security import can_edit, can_view, is_admin
from ..services import hosts, mail, seclog, store

router = APIRouter(prefix="/api/settings", tags=["settings"])


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    default_due_days: int = Field(14, ge=1, le=120)


class EmailIn(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)


class DeliveryIn(BaseModel):
    mode: Literal["sim", "graph", "smtp"]
    tenant: str = ""
    client: str = ""
    auth_type: Literal["secret", "cert"] = "secret"
    cert_thumbprint: str = ""
    save_sent: bool = True
    host: str = ""
    port: int = Field(587, ge=1, le=65535)
    security: Literal["starttls", "tls", "none"] = "starttls"
    smtp_auth: Literal["none", "login"] = "none"
    username: str = ""
    mailbox: str = ""
    display_name: str = "QE Connect"
    reply_to: str = ""
    rate_per_minute: int = Field(30, ge=1, le=600)
    link_base: str = ""


class TestIn(BaseModel):
    to: str


def delivery_out(db: Session) -> dict:
    d = store.get(db, "delivery")
    return {**d, "server": {"client_secret_set": bool(cfg.mail_client_secret), "smtp_password_set": bool(cfg.smtp_password),
                            "cert_path_set": bool(cfg.mail_cert_path), "public_url": cfg.public_url},
            "problems": mail.config_problems(d)}


@router.get("")
def all_settings(db: Session = Depends(get_db), _: User = Depends(can_view)):
    return {"campaign": store.get(db, "campaign"), "email": store.get(db, "email"), "delivery": delivery_out(db),
            "placeholders": ["{first_name}", "{name}", "{application}", "{project_id}", "{lob}", "{team}",
                             "{due_date}", "{survey_link}"]}


@router.put("/campaign")
def put_campaign(body: CampaignIn, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    store.put(db, "campaign", body.model_dump())
    store.log(db, me.email, "settings.campaign", body.name)
    db.commit()
    return store.get(db, "campaign")


@router.put("/email")
def put_email(body: EmailIn, db: Session = Depends(get_db), me: User = Depends(can_edit)):
    if "{survey_link}" not in body.body:
        raise HTTPException(422, "The message needs the {survey_link} placeholder, or respondents can't open the survey.")
    store.put(db, "email", {"subject": mail.one_line(body.subject), "body": body.body})
    store.log(db, me.email, "settings.email", "Updated the invitation email")
    db.commit()
    return store.get(db, "email")


@router.post("/email/reset")
def reset_email(db: Session = Depends(get_db), me: User = Depends(can_edit)):
    store.put(db, "email", dict(store.DEFAULT_EMAIL))
    store.log(db, me.email, "settings.email", "Restored the default invitation email")
    db.commit()
    return store.get(db, "email")


@router.put("/delivery")
def put_delivery(body: DeliveryIn, db: Session = Depends(get_db), me: User = Depends(is_admin)):
    data = body.model_dump()
    for k in ("tenant", "client", "cert_thumbprint", "host", "username", "mailbox", "display_name", "reply_to", "link_base"):
        data[k] = mail.one_line(data[k])
    if data["mailbox"] and not mail.email_ok(data["mailbox"]):
        raise HTTPException(422, "The sending mailbox isn't a valid email address.")
    if data["reply_to"] and not mail.email_ok(data["reply_to"]):
        raise HTTPException(422, "The reply-to address isn't a valid email address.")
    if data["link_base"] and not data["link_base"].lower().startswith(("http://", "https://")):
        raise HTTPException(422, "The survey link address must start with https:// (or http:// for testing).")
    data["link_base"] = data["link_base"].rstrip("/")
    before = store.get(db, "delivery")
    data["tested"] = None if any(before.get(k) != v for k, v in data.items()) else before.get("tested")
    store.put(db, "delivery", data)
    store.log(db, me.email, "settings.delivery", f"Email delivery set to {data['mode']}")
    seclog.record(db, "settings.delivery", me.email, detail=f"Email delivery set to {data['mode']} ({data['mailbox'] or 'no mailbox'})")
    db.commit()
    hosts.refresh(data["link_base"])
    return delivery_out(db)


@router.post("/delivery/test")
def test_delivery(body: TestIn, db: Session = Depends(get_db), me: User = Depends(is_admin)):
    return mail.test_send(db, body.to.strip(), me.email)


__all__ = ["router", "Optional"]

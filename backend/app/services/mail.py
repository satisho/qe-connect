"""Invitation emails: composing, the send queue and the delivery routes.

Routes (chosen on the Email delivery page):

* ``sim``   - not connected: emails are recorded on the Sent emails page only.
* ``graph`` - Microsoft 365 through Microsoft Graph ``sendMail`` with an Entra ID app
              registration (client secret from QEC_MAIL_CLIENT_SECRET, or a certificate
              from QEC_MAIL_CERT_PATH plus its thumbprint).
* ``smtp``  - an SMTP relay such as an Exchange receive connector or an Exchange Online
              relay connector (optional sign-in with QEC_SMTP_PASSWORD).

Emails are queued in the database and a background worker sends them, pacing itself to
the "most emails per minute" setting so Exchange throttling is not hit.
"""
from __future__ import annotations

import html
import json
import logging
import re
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Application, Email, Invitation, utcnow
from . import store

log = logging.getLogger("qe_connect.mail")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


class MailError(Exception):
    pass


CONTROL_RE = re.compile(r"[\x00-\x1f\x7f\u2028\u2029]+")


def one_line(text: str | None) -> str:
    """Single-line text for names and email headers: line breaks and control characters become spaces."""
    return re.sub(r"\s{2,}", " ", CONTROL_RE.sub(" ", text or "")).strip()


def email_ok(addr: str | None) -> bool:
    return bool(addr and EMAIL_RE.match(addr.strip()))


def link_base(db: Session) -> str:
    return (store.get(db, "delivery").get("link_base") or settings.public_url).rstrip("/")


def survey_link(db: Session, token: str) -> str:
    return f"{link_base(db)}/s/{token}"


def _due_text(dt: datetime | None) -> str:
    if not dt:
        return "the date the assessment team gave you"
    return f"{dt.strftime('%A')}, {dt.strftime('%B')} {dt.day}"


def fill(template: str, app: Application, inv: Invitation | None, link: str, org: dict | None = None) -> str:
    org = org or {}
    values = {
        "organization": org.get("name") or "your organization",
        "team_name": org.get("team_name") or "QE Assessment team",
        "first_name": (app.respondent_name or "there").split(" ")[0],
        "name": app.respondent_name or "",
        "application": app.name,
        "project_id": app.project_id or "",
        "lob": app.lob.name if app.lob else "",
        "team": app.team or "",
        "due_date": _due_text(inv.due_at if inv else None),
        "survey_link": link,
    }
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), template)


LINK_RE = re.compile(r"(https?://[^\s<]+/s/[A-Za-z0-9_-]+)")


def to_html(body: str, accent: str = "") -> str:
    accent = accent if re.fullmatch(r"#[0-9A-Fa-f]{6}", accent or "") else store.ACCENT_FALLBACK
    parts = []
    for para in re.split(r"\n{2,}", body.strip()):
        h = html.escape(para).replace("\n", "<br>")
        h = LINK_RE.sub(
            lambda m: (
                f'</p><p><a href="{m.group(1)}" style="display:inline-block;background:{accent};color:#ffffff;'
                f'padding:10px 18px;border-radius:6px;text-decoration:none;font-weight:600">Start the survey</a>'
                f'<br><span style="font-size:12px;color:#536677">{m.group(1)}</span>'
            ),
            h,
        )
        parts.append(f"<p>{h}</p>")
    return (
        '<div style="font-family:Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.5;color:#0F2233;max-width:600px">'
        + "".join(parts) + "</div>"
    )


def from_line(d: dict) -> str:
    return formataddr((d.get("display_name") or "QE Connect", d.get("mailbox") or ""))


def compose(db: Session, app: Application, inv: Invitation, kind: str, actor: str) -> Email:
    d = store.get(db, "delivery")
    tpl = store.get(db, "email")
    link = survey_link(db, inv.token)
    o = store.org(db)
    subject = one_line(("Reminder: " if kind == "Reminder" else "") + fill(tpl["subject"], app, inv, link, o))
    mode = d.get("mode", "sim")
    e = Email(
        application_id=app.id, kind=kind, to_addr=app.respondent_email.strip(), to_name=one_line(app.respondent_name),
        from_addr=from_line(d), subject=subject[:500], body=fill(tpl["body"], app, inv, link, o),
        status="recorded" if mode == "sim" else "queued", via=mode, created_by=actor,
        sent_at=utcnow() if mode == "sim" else None,
    )
    db.add(e)
    return e


# ---------------------------------------------------------------- delivery routes
_msal_apps: dict = {}


def _graph_token(d: dict) -> str:
    try:
        import msal
    except ImportError as exc:  # pragma: no cover
        raise MailError("The msal package is not installed. Run the start script again.") from exc
    if d.get("auth_type") == "cert":
        path = settings.mail_cert_path
        if not path:
            raise MailError("Set QEC_MAIL_CERT_PATH to the certificate's private key file (PEM).")
        try:
            key = open(path, encoding="utf-8").read()
        except OSError as exc:
            raise MailError(f"Could not read the certificate file: {exc}") from exc
        cred = {"private_key": key, "thumbprint": (d.get("cert_thumbprint") or "").replace(":", "").strip()}
    else:
        if not settings.mail_client_secret:
            raise MailError("Set QEC_MAIL_CLIENT_SECRET on the server, then restart QE Connect.")
        cred = settings.mail_client_secret
    key_id = (d["tenant"], d["client"], d.get("auth_type"))
    app = _msal_apps.get(key_id)
    if app is None:
        app = msal.ConfidentialClientApplication(
            d["client"], authority=f"https://login.microsoftonline.com/{d['tenant']}", client_credential=cred)
        _msal_apps[key_id] = app
    res = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in res:
        raise MailError(f"Microsoft sign-in failed: {res.get('error_description') or res.get('error') or res}")
    return res["access_token"]


def _send_graph(d: dict, e: Email) -> None:
    token = _graph_token(d)
    msg = {
        "message": {
            "subject": one_line(e.subject),
            "body": {"contentType": "HTML", "content": to_html(e.body, d.get("_accent", ""))},
            "toRecipients": [{"emailAddress": {"address": e.to_addr, "name": e.to_name or e.to_addr}}],
        },
        "saveToSentItems": bool(d.get("save_sent", True)),
    }
    if email_ok(d.get("reply_to")):
        msg["message"]["replyTo"] = [{"emailAddress": {"address": d["reply_to"]}}]
    req = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0/users/{urllib.request.quote(d['mailbox'])}/sendMail",
        data=json.dumps(msg).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status not in (200, 202):
                raise MailError(f"Microsoft Graph answered {r.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise MailError(f"Microsoft Graph refused the message ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise MailError(f"Could not reach graph.microsoft.com: {exc.reason}") from exc


def _send_smtp(d: dict, e: Email) -> None:
    m = EmailMessage()
    m["From"] = from_line(d)
    m["To"] = formataddr((one_line(e.to_name), e.to_addr))
    if email_ok(d.get("reply_to")):
        m["Reply-To"] = d["reply_to"]
    m["Subject"] = one_line(e.subject)
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain=(d.get("mailbox") or "qe-connect.local").split("@")[-1])
    m.set_content(e.body)
    m.add_alternative(to_html(e.body, d.get("_accent", "")), subtype="html")
    host, port = d.get("host", "").strip(), int(d.get("port") or 25)
    ctx = ssl.create_default_context()
    try:
        if d.get("security") == "tls":
            server = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
        with server:
            server.ehlo()
            if d.get("security") == "starttls":
                server.starttls(context=ctx)
                server.ehlo()
            if d.get("smtp_auth") == "login":
                if not settings.smtp_password:
                    raise MailError("Set QEC_SMTP_PASSWORD on the server, then restart QE Connect.")
                server.login(d.get("username", ""), settings.smtp_password)
            server.send_message(m)
    except MailError:
        raise
    except smtplib.SMTPException as exc:
        raise MailError(f"The mail server refused the message: {exc}") from exc
    except OSError as exc:
        raise MailError(f"Could not connect to {host}:{port}: {exc}") from exc


def deliver(d: dict, e: Email) -> None:
    mode = d.get("mode", "sim")
    if mode == "graph":
        _send_graph(d, e)
    elif mode == "smtp":
        _send_smtp(d, e)


def config_problems(d: dict) -> list[str]:
    p = []
    mode = d.get("mode", "sim")
    if mode == "sim":
        return p
    if not email_ok(d.get("mailbox")):
        p.append("Enter the mailbox to send from.")
    if mode == "graph":
        if not GUID_RE.match(d.get("tenant", "") or ""):
            p.append("The tenant ID should be a GUID like 1a2b3c4d-1111-2222-3333-444455556666.")
        if not GUID_RE.match(d.get("client", "") or ""):
            p.append("The client ID should be a GUID.")
        if d.get("auth_type") == "cert":
            if not d.get("cert_thumbprint"):
                p.append("Add the certificate thumbprint.")
            if not settings.mail_cert_path:
                p.append("Set QEC_MAIL_CERT_PATH on the server.")
        elif not settings.mail_client_secret:
            p.append("Set QEC_MAIL_CLIENT_SECRET on the server.")
    if mode == "smtp":
        if not (d.get("host") or "").strip():
            p.append("Enter the SMTP server.")
        try:
            if not 0 < int(d.get("port")) < 65536:
                raise ValueError
        except (TypeError, ValueError):
            p.append("Enter a port, for example 25 or 587.")
        if d.get("smtp_auth") == "login":
            if not d.get("username"):
                p.append("Enter the SMTP username.")
            if not settings.smtp_password:
                p.append("Set QEC_SMTP_PASSWORD on the server.")
    return p


def test_send(db: Session, to: str, actor: str) -> dict:
    d = {**store.get(db, "delivery"), "_accent": store.org(db)["accent"]}
    steps = []
    ok = True
    if not email_ok(to):
        steps.append({"ok": False, "text": "Enter a valid test recipient address."})
        ok = False
    probs = config_problems(d)
    steps += [{"ok": False, "text": p} for p in probs]
    ok = ok and not probs
    if ok:
        steps.append({"ok": True, "text": f"Settings complete for {'Microsoft 365 (Graph)' if d['mode'] == 'graph' else 'SMTP relay' if d['mode'] == 'smtp' else 'recording only'}"})
        e = Email(kind="Test", to_addr=to, to_name="", from_addr=from_line(d), via=d["mode"], created_by=actor,
                  subject="QE Connect test email",
                  body="This is a test from QE Connect. If you can read it, email delivery is working.\n\nQE Connect")
        try:
            deliver(d, e)
            e.status = "sent" if d["mode"] != "sim" else "recorded"
            e.sent_at = utcnow()
            steps.append({"ok": True, "text": (f"Sent a test message to {to}" if d["mode"] != "sim"
                                              else "Recorded a test message. Not connected, so nothing left the server.")})
        except Exception as exc:  # MailError or anything unexpected
            e.status = "failed"
            e.error = str(exc)
            ok = False
            steps.append({"ok": False, "text": str(exc) if isinstance(exc, MailError) else f"Couldn't send: {exc}"})
        db.add(e)
    result = {"ok": ok, "at": utcnow().isoformat(), "mode": d["mode"], "steps": steps}
    store.put(db, "delivery", {"tested": result})
    store.log(db, actor, "mail.test", f"Test email to {to}: {'ok' if ok else 'failed'}")
    db.commit()
    return result


# ---------------------------------------------------------------- queue worker
_sent_times: deque = deque()


def send_pending(session_factory: Callable[[], Session], max_batch: int = 50) -> int:
    """Send queued emails, respecting the per-minute rate. Returns how many were attempted."""
    db = session_factory()
    done = 0
    try:
        d = {**store.get(db, "delivery"), "_accent": store.org(db)["accent"]}
        rate = max(1, int(d.get("rate_per_minute") or 30))
        queued = db.scalars(select(Email).where(Email.status == "queued").order_by(Email.id).limit(max_batch)).all()
        for e in queued:
            now = time.monotonic()
            while _sent_times and now - _sent_times[0] > 60:
                _sent_times.popleft()
            if len(_sent_times) >= rate:
                break
            if d.get("mode") == "sim" or e.via != d.get("mode"):
                e.via = d.get("mode", "sim")
            e.attempts += 1
            try:
                if d.get("mode") == "sim":
                    e.status = "recorded"
                else:
                    deliver(d, e)
                    e.status = "sent"
                e.sent_at = utcnow()
                e.error = ""
            except MailError as exc:
                e.error = str(exc)
                e.status = "failed" if e.attempts >= 3 else "queued"
                log.warning("Email %s to %s failed: %s", e.id, e.to_addr, exc)
            except Exception as exc:  # anything unexpected: fail this email, keep the queue moving
                e.error = f"Couldn't send this email: {exc}"
                e.status = "failed"
                log.exception("Email %s to %s failed unexpectedly", e.id, e.to_addr)
            _sent_times.append(time.monotonic())
            db.commit()
            done += 1
            if e.status == "queued":  # back off after a failure
                break
    finally:
        db.close()
    return done


class MailWorker:
    def __init__(self, session_factory: Callable[[], Session], interval: float = 3.0):
        self.session_factory = session_factory
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="qe-mail", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                send_pending(self.session_factory)
            except Exception:  # keep the worker alive
                log.exception("Mail worker error")
            self._stop.wait(self.interval)

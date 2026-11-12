"""One or more tests for each finding fixed in the 1.0.1 security release."""
import io
import logging
import time
import zipfile
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select, update

from app import db as dbmod
from app.main import MaskSurveyLinks, create_app
from app.models import Email, SecurityEvent, UserSession, utcnow
from app.services import mail, totp
from conftest import PW


def _apps(c):
    return {a["name"]: a for a in c.get("/api/tracker").json()["applications"]}


def _events(kind=None):
    s = dbmod.SessionLocal()
    try:
        q = select(SecurityEvent).order_by(SecurityEvent.id)
        if kind:
            q = q.where(SecurityEvent.kind == kind)
        return [(e.kind, e.outcome, e.actor) for e in s.scalars(q)]
    finally:
        s.close()


# ---------------------------------------------------------------- SEC-01
def test_sec01_line_breaks_removed_and_queue_never_stalls(sampled, monkeypatch):
    c = sampled
    a = _apps(c)["Field service mobile"]
    r = c.patch(f"/api/applications/{a['id']}", json={"name": "Field\nservice\r\napp"})
    assert r.json()["name"] == "Field service app"
    c.put("/api/settings/delivery", json={"mode": "smtp", "host": "127.0.0.1", "port": 2526, "security": "none",
                                          "mailbox": "qe-connect@example.com"})
    c.post("/api/invitations/send", json={"application_ids": [a["id"], _apps(c)["Contact centre CRM"]["id"]]})
    calls = []

    def flaky(d, e):
        calls.append(e.id)
        if len(calls) == 1:
            raise ValueError("unexpected header problem")

    monkeypatch.setattr(mail, "deliver", flaky)
    mail._sent_times.clear()
    mail.send_pending(dbmod.SessionLocal)
    s = dbmod.SessionLocal()
    statuses = [e.status for e in s.scalars(select(Email).where(Email.id.in_(calls)).order_by(Email.id))]
    s.close()
    assert statuses == ["failed", "sent"]


# ---------------------------------------------------------------- SEC-02
def _xlsx_bytes(sheets=1, filler=0):
    wb = Workbook()
    ws = wb.active
    ws.append(["Q ID", "Question"])
    ws.append(["Z1", "x" * filler if filler else "Hello?"])
    for i in range(sheets - 1):
        wb.create_sheet(f"S{i}")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_sec02_hardened_parser_and_workbook_limits(admin):
    from openpyxl.xml import DEFUSEDXML

    assert DEFUSEDXML is True
    r = admin.post("/api/questions/import", data={"mode": "replace"}, files={"file": ("many.xlsx", _xlsx_bytes(sheets=61), "application/octet-stream")})
    assert r.status_code == 422 and "too many" in r.json()["detail"]
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/worksheets/sheet1.xml", "<a>" + "A" * 120_000_000 + "</a>")
    r = admin.post("/api/questions/import", data={"mode": "replace"}, files={"file": ("bomb.xlsx", bomb.getvalue(), "application/octet-stream")})
    assert r.status_code == 422 and "too large" in r.json()["detail"]
    ok = admin.post("/api/questions/import", data={"mode": "replace"}, files={"file": ("ok.xlsx", _xlsx_bytes(), "application/octet-stream")})
    assert ok.status_code == 200


# ---------------------------------------------------------------- SEC-03
def test_sec03_request_size_limits(sampled):
    big = {"answers": {"B1": "x" * 1_200_000}, "mode": "core"}
    assert sampled.put("/api/s/any-token", json=big).status_code == 413
    assert sampled.post("/api/auth/login", json={"email": "a@b.co", "password": "p" * 1_100_000}).status_code == 413
    r = sampled.post("/api/applications/import", data={"mode": "add"}, files={"file": ("big.csv", b"a" * (12 * 1024 * 1024), "text/csv")})
    assert r.status_code == 413
    # a normal-sized upload still works
    r = sampled.post("/api/applications/import", data={"mode": "add", "text": "Application\nSmall one\n"})
    assert r.status_code == 200


# ---------------------------------------------------------------- SEC-04
def test_sec04_survey_links_masked_in_access_log():
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "GET", "/api/s/AbC_dEf-123?x=1", "1.1", 200), None)
    MaskSurveyLinks().filter(rec)
    assert "AbC_dEf-123" not in rec.getMessage() and "/api/s/[link]" in rec.getMessage()


# ---------------------------------------------------------------- SEC-05
def _code(secret, offset=0):
    return totp.code_at(secret, int(time.time() // 30) + offset)


def test_sec05_totp_known_vector():
    # RFC 6238 test secret "12345678901234567890" at T=59s gives 287082 for 6 digits (SHA-1)
    import base64

    secret = base64.b32encode(b"12345678901234567890").decode()
    assert totp.code_at(secret, 59 // 30) == "287082"


def test_sec05_mfa_setup_signin_and_replay(admin):
    c = admin
    start = c.post("/api/auth/mfa/setup/start").json()
    assert start["qr"].startswith("data:image/svg+xml;base64,") and start["uri"].startswith("otpauth://totp/")
    assert c.post("/api/auth/mfa/setup/confirm", json={"code": "000000"}).status_code == 422
    assert c.post("/api/auth/mfa/setup/confirm", json={"code": _code(start["secret"])}).status_code == 200
    assert c.get("/api/auth/state").json()["user"]["mfa_enabled"] is True
    c.post("/api/auth/logout")
    r = c.post("/api/auth/login", json={"email": "ada@example.com", "password": PW})
    assert r.json()["pending"]["step"] == "verify" and r.json()["user"] is None
    assert c.get("/api/tracker").status_code == 401  # password alone is not enough
    assert c.post("/api/auth/mfa/verify", json={"code": "123456"}).status_code == 401
    code = _code(start["secret"], 1)
    assert c.post("/api/auth/mfa/verify", json={"code": code}).status_code == 200
    assert c.get("/api/tracker").status_code == 200
    # the same code can't be used twice
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"email": "ada@example.com", "password": PW})
    assert c.post("/api/auth/mfa/verify", json={"code": code}).status_code == 401


def test_sec05_policy_requires_mfa_and_admin_reset(admin):
    c = admin
    c.post("/api/users", json={"name": "Ed", "email": "ed@example.com", "role": "editor", "password": PW})
    assert c.put("/api/security/policy", json={"mfa_required": True, "idle_minutes": 30}).json()["mfa_required"] is True
    c.post("/api/auth/logout")
    r = c.post("/api/auth/login", json={"email": "ed@example.com", "password": PW}).json()
    assert r["pending"]["step"] == "setup"
    assert c.get("/api/applications").status_code == 401
    secret = c.post("/api/auth/mfa/setup/start").json()["secret"]
    assert c.post("/api/auth/mfa/setup/confirm", json={"code": _code(secret)}).status_code == 200
    assert c.get("/api/applications").status_code == 200
    assert c.post("/api/auth/mfa/disable", json={"password": PW}).status_code == 409  # policy forbids turning it off
    c.post("/api/auth/logout")
    # admin (no MFA yet) must set it up too, then resets Ed's
    r = c.post("/api/auth/login", json={"email": "ada@example.com", "password": PW}).json()
    assert r["pending"]["step"] == "setup"
    s2 = c.post("/api/auth/mfa/setup/start").json()["secret"]
    c.post("/api/auth/mfa/setup/confirm", json={"code": _code(s2)})
    ed = [u for u in c.get("/api/users").json() if u["email"] == "ed@example.com"][0]
    assert ed["mfa_enabled"] is True
    assert c.patch(f"/api/users/{ed['id']}", json={"reset_mfa": True}).json()["mfa_enabled"] is False


def test_sec05_pending_session_expires(admin):
    c = admin
    secret = c.post("/api/auth/mfa/setup/start").json()["secret"]
    c.post("/api/auth/mfa/setup/confirm", json={"code": _code(secret)})
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"email": "ada@example.com", "password": PW})
    s = dbmod.SessionLocal()
    s.execute(update(UserSession).values(expires_at=utcnow() - timedelta(seconds=1)))
    s.commit()
    s.close()
    assert c.post("/api/auth/mfa/verify", json={"code": _code(secret, 1)}).status_code == 401


# ---------------------------------------------------------------- SEC-06
def test_sec06_security_log(admin):
    c = admin
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"email": "ada@example.com", "password": "Wrong-pass-1"})
    c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong-pass-1"})
    c.post("/api/auth/login", json={"email": "ada@example.com", "password": PW})
    c.post("/api/users", json={"name": "Vi", "email": "vi@example.com", "role": "viewer", "password": PW})
    kinds = _events()
    assert ("signin", "fail", "ada@example.com") in kinds and ("signin", "fail", "nobody@example.com") in kinds
    assert ("signout", "ok", "ada@example.com") in kinds and ("signin", "ok", "ada@example.com") in kinds
    assert ("user.create", "ok", "ada@example.com") in kinds
    ev = c.get("/api/security/events?outcome=fail").json()
    assert ev and all(e["outcome"] == "fail" for e in ev)
    csvr = c.get("/api/security/events/download")
    assert csvr.status_code == 200 and "signin" in csvr.content.decode("utf-8-sig")
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"email": "vi@example.com", "password": PW})
    assert c.get("/api/security/events").status_code == 403


def test_sec06_exports_and_deletions_logged(sampled):
    c = sampled
    a = _apps(c)["Customer portal"]
    c.get(f"/api/responses/{a['id']}/download?fmt=csv")
    c.delete(f"/api/applications/{_apps(c)['Warehouse sensors (OT)']['id']}")
    kinds = [k for k, _, _ in _events()]
    assert "export.response" in kinds and "delete.application" in kinds and "delete.all" in kinds


# ---------------------------------------------------------------- SEC-07
def test_sec07_https_headers_and_secure_cookie(client):
    c = TestClient(client.app, base_url="https://testserver", headers={"X-QEC": "1"})
    r = c.post("/api/auth/setup", json={"name": "A", "email": "a@example.com", "password": PW})
    assert "secure" in r.headers["set-cookie"].lower()
    h = c.get("/api/health").headers
    assert h["strict-transport-security"].startswith("max-age=")
    assert "camera=()" in h["permissions-policy"]
    assert "strict-transport-security" not in client.get("/api/health").headers  # not sent over plain HTTP


# ---------------------------------------------------------------- SEC-08
def test_sec08_idle_timeout(admin):
    c = admin
    assert c.get("/api/tracker").status_code == 200
    s = dbmod.SessionLocal()
    s.execute(update(UserSession).values(last_seen_at=utcnow() - timedelta(minutes=31)))
    s.commit()
    s.close()
    r = c.get("/api/tracker")
    assert r.status_code == 401 and "without activity" in r.json()["detail"]
    assert ("session.idle", "ok", "ada@example.com") in _events()


# ---------------------------------------------------------------- SEC-09
def test_sec09_throttle_survives_restart(admin):
    c = admin
    c.post("/api/auth/logout")
    for _ in range(5):
        c.post("/api/auth/login", json={"email": "ada@example.com", "password": "Wrong-pass-1"})
    fresh = TestClient(create_app(run_startup=False), headers={"X-QEC": "1"})  # as after a restart
    r = fresh.post("/api/auth/login", json={"email": "ada@example.com", "password": PW})
    assert r.status_code == 429
    assert ("signin", "blocked", "ada@example.com") in _events()


def test_sec09_per_address_limit(admin):
    c = admin
    c.post("/api/auth/logout")
    for i in range(20):
        c.post("/api/auth/login", json={"email": f"guess{i}@example.com", "password": "Wrong-pass-1"})
    assert c.post("/api/auth/login", json={"email": "ada@example.com", "password": PW}).status_code == 429


# ---------------------------------------------------------------- SEC-10
def test_sec10_reference_independent_of_link(sampled):
    c = sampled
    c.post("/api/invitations/send", json={"application_ids": [_apps(c)["Field service mobile"]["id"]]})
    em = [e for e in c.get("/api/emails").json() if e["application"] == "Field service mobile"][0]
    tok = em["body"].split("/s/")[1].split()[0]
    ref = c.get(f"/api/s/{tok}").json()["reference"]
    assert ref.startswith("QEA-") and tok[:6].upper() not in ref


# ---------------------------------------------------------------- SEC-12
def test_sec12_unknown_host_refused(sampled):
    c = sampled
    assert c.get("/api/health", headers={"Host": "evil.example.com"}).status_code == 400
    assert c.get("/api/health", headers={"Host": "localhost:8000"}).status_code == 200
    c.put("/api/settings/delivery", json={"mode": "sim", "link_base": "https://qe-connect.example.local"})
    assert c.get("/api/health", headers={"Host": "qe-connect.example.local"}).status_code == 200


# ---------------------------------------------------------------- SEC-14
def test_sec14_backup_needs_strong_password(sampled):
    assert sampled.post("/api/workspace/export", json={"password": "short"}).status_code == 422


@pytest.mark.parametrize("path", ["/api/auth/state", "/"])
def test_core_headers_everywhere(client, path):
    h = client.get(path).headers
    assert h["x-frame-options"] == "DENY" and "default-src 'self'" in h["content-security-policy"]

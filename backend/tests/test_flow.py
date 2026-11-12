"""The full loop: send an invitation, respond through the link, track and download."""
import csv
import io

from openpyxl import load_workbook

from app import db as dbmod
from app.services import mail


def _app(c, name):
    return [a for a in c.get("/api/tracker").json()["applications"] if a["name"] == name][0]


def _token(c, name):
    e = [e for e in c.get("/api/emails").json() if e["application"] == name][0]
    return e["body"].split("/s/")[1].split()[0]


def test_send_respond_track_download(sampled):
    c = sampled
    vessel = _app(c, "Field service mobile")
    assert vessel["status"] == "notsent"
    r = c.post("/api/invitations/send", json={"application_ids": [vessel["id"], _app(c, "Warehouse sensors (OT)")["id"]],
                                               "due_date": "2099-11-10"})
    body = r.json()
    assert body["sent"] == 1 and body["skipped"][0]["reason"] == "no valid respondent email"
    em = [e for e in c.get("/api/emails").json() if e["application"] == "Field service mobile"][0]
    assert em["status"] == "recorded" and "Tuesday, November 10" in em["body"] and "/s/" in em["body"]
    assert _app(c, "Field service mobile")["status"] == "sent"

    tok = _token(c, "Field service mobile")
    s = c.get(f"/api/s/{tok}").json()
    assert s["application"]["name"] == "Field service mobile"
    assert s["answers"]["A2"] == "Operations & Enterprise Systems"
    assert s["answers"]["A3"] == "Field service mobile (PRJ-1121)"
    assert set(s["prefilled"]) >= {"A1", "A2", "A3", "A4"}
    assert _app(c, "Field service mobile")["status"] == "opened"

    answers = dict(s["answers"])
    answers.update({"B1": "Mobile app for engineers", "B2": "Custom-built by an in-house team", "B3": "=HYPERLINK(1)",
                    "B4": ["Mobile app - Android", "Not a real option"], "B5": "Safety-critical",
                    "B7": "In build / implementation", "B8": "1-3", "L9": "4"})
    r = c.put(f"/api/s/{tok}", json={"answers": answers, "other": {}, "mode": "core"})
    assert r.status_code == 200
    t = _app(c, "Field service mobile")
    assert t["status"] == "progress" and 0 < t["answered"] < t["total"]

    r = c.post(f"/api/s/{tok}/submit", json={"answers": answers, "other": {}, "mode": "core"})
    assert r.status_code == 422
    missing = {p["qid"] for p in r.json()["detail"]["problems"]}
    assert missing == {"M1", "M2", "M3"}

    answers.update({"M1": "In a later iteration", "M2": "Varies widely", "M3": ["Unit", "None of these"]})
    r = c.post(f"/api/s/{tok}/submit", json={"answers": answers, "other": {}, "mode": "core"})
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert r.json()["answers"]["M3"] == ["None of these"]  # exclusive option wins
    assert r.json()["answers"]["B4"] == ["Mobile app - Android"]  # unknown option dropped
    assert c.put(f"/api/s/{tok}", json={"answers": answers, "mode": "core"}).status_code == 409

    t = _app(c, "Field service mobile")
    assert t["status"] == "completed" and t["completed_at"]
    counts = c.get("/api/tracker").json()["counts"]
    assert counts["completed"] == 3

    view = c.get(f"/api/responses/{t['id']}").json()
    assert view["sections"][0]["id"] == "A"

    r = c.get(f"/api/responses/{t['id']}/download?fmt=csv")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    b3 = [x for x in rows if x[8] == "B3"][0]
    assert b3[-1] == "'=HYPERLINK(1)"  # formula injection neutralised
    l8 = [x for x in rows if x[8] == "L8"][0]
    assert l8[-1] == "(not asked)"

    r = c.get(f"/api/responses/{t['id']}/download?fmt=xlsx")
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Response"] and wb["Response"]["A2"].value == "Field service mobile"

    r = c.get("/api/responses-all/download?fmt=xlsx")
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Summary", "Answers"]
    assert wb["Summary"].max_row == 4  # header + 3 completed

    # reopen and withdraw rules
    assert c.post(f"/api/invitations/{t['id']}/reopen").status_code == 200
    assert _app(c, "Field service mobile")["status"] == "progress"
    assert c.delete(f"/api/invitations/{_app(c, 'Contact centre CRM')['id']}").status_code == 200
    assert c.get(f"/api/s/{_token(c, 'Contact centre CRM')}").status_code == 404


def test_reminders_and_bad_tokens(sampled):
    c = sampled
    crm = _app(c, "Contact centre CRM")
    r = c.post("/api/invitations/remind", json={"application_ids": [crm["id"], _app(c, "Customer portal")["id"]]})
    assert r.json()["sent"] == 1 and r.json()["skipped"][0]["name"] == "Customer portal"
    em = c.get("/api/emails").json()[0]
    assert em["kind"] == "Reminder" and em["subject"].startswith("Reminder: ")
    assert _app(c, "Contact centre CRM")["reminders"] == 1
    assert c.get("/api/s/not-a-real-token").status_code == 404
    assert c.post("/api/invitations/send", json={"application_ids": [crm["id"]], "due_date": "2001-01-01"}).status_code == 422


def test_other_needs_text(sampled):
    c = sampled
    c.post("/api/invitations/send", json={"application_ids": [_app(c, "Field service mobile")["id"]]})
    tok = _token(c, "Field service mobile")
    s = c.get(f"/api/s/{tok}").json()
    a = {**s["answers"], "B2": "Other (please specify)"}
    r = c.post(f"/api/s/{tok}/submit", json={"answers": a, "other": {}, "mode": "core"})
    msgs = {p["qid"]: p["message"] for p in r.json()["detail"]["problems"]}
    assert "Other" in msgs["B2"]


def test_mail_queue_with_smtp(sampled, smtp_server):
    c = sampled
    host, port, inbox = smtp_server
    r = c.put("/api/settings/delivery", json={"mode": "smtp", "host": host, "port": port, "security": "none",
                                               "smtp_auth": "none", "mailbox": "qe-connect@example.com",
                                               "display_name": "QE Connect", "reply_to": "qe-team@example.com",
                                               "rate_per_minute": 30, "link_base": "https://qe-connect.example.local"})
    assert r.status_code == 200, r.text
    t = c.post("/api/settings/delivery/test", json={"to": "satish@example.com"}).json()
    assert t["ok"], t
    assert len(inbox) == 1 and "satish@example.com" in inbox[0][1]
    c.post("/api/invitations/send", json={"application_ids": [_app(c, "Field service mobile")["id"]]})
    em = c.get("/api/emails").json()[0]
    assert em["status"] == "queued" and em["via"] == "smtp"
    assert mail.send_pending(dbmod.SessionLocal) == 1
    em = c.get("/api/emails").json()[0]
    assert em["status"] == "sent"
    msg = inbox[-1][2]
    assert "https://qe-connect.example.local/s/" in msg and "Reply-To: qe-team@example.com" in msg


def test_mail_failure_is_reported(sampled):
    c = sampled
    c.put("/api/settings/delivery", json={"mode": "smtp", "host": "127.0.0.1", "port": 1, "security": "none",
                                          "mailbox": "qe-connect@example.com"})
    t = c.post("/api/settings/delivery/test", json={"to": "x@example.com"}).json()
    assert not t["ok"] and "Could not connect" in t["steps"][-1]["text"]
    c.post("/api/invitations/send", json={"application_ids": [_app(c, "Field service mobile")["id"]]})
    for _ in range(3):
        mail._sent_times.clear()
        mail.send_pending(dbmod.SessionLocal)
    em = c.get("/api/emails").json()[0]
    assert em["status"] == "failed" and em["error"]
    assert _app(c, "Field service mobile")["email_failed"] is True
    assert c.post(f"/api/emails/{em['id']}/retry").status_code == 200


def test_graph_route(sampled, monkeypatch):
    c = sampled
    sent = {}

    class FakeResp:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        sent["url"], sent["auth"], sent["body"] = req.full_url, req.headers["Authorization"], req.data
        return FakeResp()

    monkeypatch.setattr(mail, "_graph_token", lambda d: "tok123")
    monkeypatch.setattr(mail.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mail.settings, "mail_client_secret", "s3cret")
    r = c.put("/api/settings/delivery", json={"mode": "graph", "tenant": "1a2b3c4d-1111-2222-3333-444455556666",
                                               "client": "9f8e7d6c-1111-2222-3333-444455556666",
                                               "mailbox": "qe-connect@example.com"})
    assert r.json()["problems"] == []
    t = c.post("/api/settings/delivery/test", json={"to": "satish@example.com"}).json()
    assert t["ok"]
    assert sent["url"].endswith("/users/qe-connect%40example.com/sendMail") and sent["auth"] == "Bearer tok123"
    s = c.get("/api/settings").json()["delivery"]
    assert s["server"]["client_secret_set"] is True and "s3cret" not in str(s)


def test_workspace_roundtrip(sampled):
    c = sampled
    data = c.post("/api/workspace/export", json={"password": "Backup-Pass-2026"}).content
    assert data.startswith(b"QECB1") and b"Field service" not in data  # encrypted
    before = c.get("/api/tracker").json()["counts"]
    c.post("/api/applications/import", data={"mode": "replace", "text": "Application\nOnly one\n"})
    assert c.get("/api/tracker").json()["total"] == 1
    r = c.post("/api/workspace/import", files={"file": ("b.qecbackup", data, "application/octet-stream")}, data={"password": "wrong-Pass-1"})
    assert r.status_code == 422 and "password" in r.json()["detail"]
    r = c.post("/api/workspace/import", files={"file": ("b.qecbackup", data, "application/octet-stream")}, data={"password": "Backup-Pass-2026"})
    assert r.status_code == 200, r.text
    assert c.get("/api/tracker").json()["counts"] == before
    assert c.post("/api/workspace/import", files={"file": ("b.json", b"{}", "application/json")}).status_code == 422

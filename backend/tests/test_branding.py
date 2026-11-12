"""QE Connect 2.0 is client-neutral: each install carries its own organization name, team name and colour."""
import pathlib

from app.services import mail
from tests.conftest import PW


def _token(c, name):
    e = [e for e in c.get("/api/emails").json() if e["application"] == name][0]
    return e["body"].split("/s/")[1].split()[0], e


def test_setup_takes_organization_name(client):
    r = client.post("/api/auth/setup", json={"name": "Ada", "email": "ada@example.com", "password": PW,
                                             "organization": "  Contoso   Health "})
    assert r.status_code == 200
    st = client.get("/api/auth/state").json()
    assert st["organization"]["name"] == "Contoso Health"
    assert st["organization"]["team_name"] == "QE Assessment team"
    assert st["version"] == "2.0.0"


def test_neutral_defaults_without_organization(sampled):
    st = sampled.get("/api/auth/state").json()
    assert st["organization"] == {"name": "", "team_name": "QE Assessment team", "accent": ""}
    sampled.post("/api/invitations/send", json={"application_ids": [
        [a for a in sampled.get("/api/tracker").json()["applications"] if a["name"] == "Field service mobile"][0]["id"]]})
    _, e = _token(sampled, "Field service mobile")
    assert "your organization" in e["body"] and "{organization}" not in e["body"]


def test_admin_sets_branding_used_in_emails_and_survey(sampled):
    r = sampled.put("/api/settings/organization", json={"name": "Fabrikam Bank", "team_name": "Quality CoE",
                                                        "accent": "#7a1f5c"})
    assert r.status_code == 200 and r.json()["accent"] == "#7A1F5C"
    assert "{organization}" in sampled.get("/api/settings").json()["placeholders"]
    app_id = [a for a in sampled.get("/api/tracker").json()["applications"] if a["name"] == "Field service mobile"][0]["id"]
    sampled.post("/api/invitations/send", json={"application_ids": [app_id]})
    tok, e = _token(sampled, "Field service mobile")
    assert "across Fabrikam Bank applications" in e["body"] and e["body"].rstrip().endswith("Quality CoE")
    s = sampled.get(f"/api/s/{tok}").json()
    assert s["organization"]["name"] == "Fabrikam Bank" and s["organization"]["accent"] == "#7A1F5C"
    assert "background:#7A1F5C" in mail.to_html(e["body"], "#7A1F5C")
    assert "Quality CoE" in sampled.get("/api/s/not-a-real-token").json()["detail"]


def test_branding_validation_and_roles(sampled):
    assert sampled.put("/api/settings/organization", json={"accent": "red; x"}).status_code == 422
    assert sampled.put("/api/settings/organization", json={"name": "x" * 121}).status_code == 422
    sampled.post("/api/users", json={"name": "Ed", "email": "ed@example.com", "role": "editor", "password": PW})
    sampled.post("/api/auth/logout")
    sampled.post("/api/auth/login", json={"email": "ed@example.com", "password": PW})
    assert sampled.put("/api/settings/organization", json={"name": "Nope"}).status_code == 403


def test_branding_survives_backup_and_old_backups_restore(sampled):
    sampled.put("/api/settings/organization", json={"name": "Fabrikam Bank"})
    data = sampled.post("/api/workspace/export", json={"password": PW + "x"}).content
    sampled.put("/api/settings/organization", json={"name": "Changed"})
    r = sampled.post("/api/workspace/import", files={"file": ("b.qecbackup", data)}, data={"password": PW + "x"})
    assert r.status_code == 200, r.text
    assert sampled.get("/api/auth/state").json()["organization"]["name"] == "Fabrikam Bank"


def test_no_client_specific_text_ships():
    root = pathlib.Path(__file__).resolve().parents[2]
    hits = []
    for p in list(root.glob("backend/app/**/*.py")) + list(root.glob("frontend/src/**/*.ts*")) + [root / "README.md"]:
        t = p.read_text(encoding="utf-8").lower()
        if "bc ferries" in t or "bcferries" in t:
            hits.append(str(p.relative_to(root)))
    assert hits == []

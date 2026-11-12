from conftest import PW


def test_first_run_setup_then_locked(client):
    s = client.get("/api/auth/state").json()
    assert s["needs_setup"] is True and s["user"] is None
    r = client.post("/api/auth/setup", json={"name": "A", "email": "a@example.com", "password": "short"})
    assert r.status_code == 422
    assert client.post("/api/auth/setup", json={"name": "A", "email": "a@example.com", "password": PW}).status_code == 200
    assert client.get("/api/auth/state").json()["user"]["role"] == "admin"
    r = client.post("/api/auth/setup", json={"name": "B", "email": "b@example.com", "password": PW})
    assert r.status_code == 409


def test_cookie_is_httponly_strict(client):
    r = client.post("/api/auth/setup", json={"name": "A", "email": "a@example.com", "password": PW})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_csrf_header_required(admin):
    r = admin.post("/api/lobs", json={"name": "X"}, headers={"X-QEC": ""})
    assert r.status_code == 403


def test_login_logout_and_bad_password(admin):
    admin.post("/api/auth/logout")
    assert admin.get("/api/tracker").status_code == 401
    assert admin.post("/api/auth/login", json={"email": "ada@example.com", "password": "nope"}).status_code == 401
    assert admin.post("/api/auth/login", json={"email": "ADA@example.com", "password": PW}).status_code == 200
    assert admin.get("/api/tracker").status_code == 200


def test_login_throttle(admin):
    admin.post("/api/auth/logout")
    for _ in range(5):
        admin.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-pass"})
    r = admin.post("/api/auth/login", json={"email": "ada@example.com", "password": PW})
    assert r.status_code == 429


def test_roles(admin):
    r = admin.post("/api/users", json={"name": "Vi", "email": "vi@example.com", "role": "viewer", "password": PW})
    assert r.status_code == 200
    admin.post("/api/auth/logout")
    admin.post("/api/auth/login", json={"email": "vi@example.com", "password": PW})
    assert admin.get("/api/tracker").status_code == 200
    assert admin.post("/api/lobs", json={"name": "X"}).status_code == 403
    assert admin.get("/api/users").status_code == 403
    assert admin.put("/api/settings/delivery", json={"mode": "sim"}).status_code == 403


def test_last_admin_protected(admin):
    me = admin.get("/api/users").json()[0]
    assert admin.patch(f"/api/users/{me['id']}", json={"role": "editor"}).status_code == 409
    assert admin.delete(f"/api/users/{me['id']}").status_code == 409


def test_deactivated_user_signed_out(admin):
    u = admin.post("/api/users", json={"name": "Ed", "email": "ed@example.com", "role": "editor", "password": PW}).json()
    assert admin.patch(f"/api/users/{u['id']}", json={"active": False}).status_code == 200
    admin.post("/api/auth/logout")
    assert admin.post("/api/auth/login", json={"email": "ed@example.com", "password": PW}).status_code == 401


def test_security_headers(client):
    r = client.get("/api/health")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert "server" not in {k.lower() for k in r.headers} or r.headers.get("server") != "uvicorn"


def test_api_docs_off_by_default(client):
    assert client.get("/api/docs").status_code == 404

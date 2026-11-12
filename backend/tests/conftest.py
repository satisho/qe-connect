"""Test fixtures. Uses a fresh SQLite database per test, or PostgreSQL when
QEC_TEST_DATABASE_URL is set (the schema is dropped and recreated for each test)."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db as dbmod
from app.config import settings
from app.main import create_app

PW = "Correct-Horse-9"


@pytest.fixture()
def client(tmp_path):
    settings.data_dir = tmp_path
    settings.mail_worker = False
    settings.allowed_hosts = ["testserver"]
    url = os.environ.get("QEC_TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    eng = dbmod.init_engine(url)
    if url.startswith("postgresql"):
        with eng.begin() as c:
            c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    dbmod.run_migrations(url)
    app = create_app(run_startup=False)
    with TestClient(app, headers={"X-QEC": "1"}) as c:
        yield c
    eng.dispose()


@pytest.fixture()
def admin(client):
    r = client.post("/api/auth/setup", json={"name": "Ada Admin", "email": "ada@example.com", "password": PW})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def smtp_server():
    """A tiny SMTP server that accepts any message (no TLS, no auth)."""
    import socketserver
    import threading

    inbox: list = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            w = lambda s: self.wfile.write((s + "\r\n").encode())  # noqa: E731
            w("220 test ESMTP")
            frm, rcpt = "", []
            while True:
                line = self.rfile.readline().decode(errors="replace").rstrip("\r\n")
                if not line:
                    return
                cmd = line[:4].upper()
                if cmd in ("EHLO", "HELO"):
                    w("250-test")
                    w("250 8BITMIME")
                elif cmd == "MAIL":
                    frm = line
                    w("250 OK")
                elif cmd == "RCPT":
                    rcpt.append(line)
                    w("250 OK")
                elif cmd == "DATA":
                    w("354 go")
                    data = []
                    while True:
                        ln = self.rfile.readline().decode(errors="replace")
                        if ln in (".\r\n", ".\n", ""):
                            break
                        data.append(ln)
                    inbox.append((frm, " ".join(rcpt), "".join(data)))
                    w("250 queued")
                elif cmd == "QUIT":
                    w("221 bye")
                    return
                else:
                    w("250 OK")

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield "127.0.0.1", srv.server_address[1], inbox
    srv.shutdown()
    srv.server_close()


@pytest.fixture()
def sampled(admin):
    assert admin.post("/api/sample").status_code == 200
    return admin

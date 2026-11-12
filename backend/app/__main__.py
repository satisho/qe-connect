"""Run QE Connect:  python -m app [--open] [--host H] [--port P]

Recovery:  python -m app --reset-password someone@example.com
           python -m app --reset-mfa someone@example.com
"""
from __future__ import annotations

import argparse
import getpass
import logging
import sys
import threading
import time
import webbrowser


def main() -> None:
    from .config import APP_VERSION, settings

    p = argparse.ArgumentParser(prog="qe-connect", description=f"QE Connect {APP_VERSION}")
    p.add_argument("--host", default=settings.host)
    p.add_argument("--port", type=int, default=settings.port)
    p.add_argument("--open", action="store_true", help="open the portal in your browser once it is ready")
    p.add_argument("--reset-password", metavar="EMAIL", help="set a new password for an account, then exit")
    p.add_argument("--reset-mfa", metavar="EMAIL", help="remove an account's authenticator app (lost phone), then exit")
    args = p.parse_args()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.reset_password:
        reset_password(args.reset_password)
        return
    if args.reset_mfa:
        reset_mfa(args.reset_mfa)
        return
    if bool(settings.tls_cert) != bool(settings.tls_key):
        sys.exit("Set both QEC_TLS_CERT and QEC_TLS_KEY to turn on HTTPS, or neither.")
    tls = bool(settings.tls_cert)

    import uvicorn

    url = f"{'https' if tls else 'http'}://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    print(f"\n  QE Connect {APP_VERSION} is starting at {url}\n  Data folder: {settings.data_dir}\n  Press Ctrl+C to stop.\n")
    if args.open:
        def _open():
            time.sleep(2.0)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()
    kw = {}
    if tls:
        kw.update(ssl_certfile=settings.tls_cert, ssl_keyfile=settings.tls_key)
    if settings.trusted_proxies:
        # Behind a reverse proxy: trust its X-Forwarded-For / -Proto so client addresses and HTTPS are seen correctly.
        kw.update(proxy_headers=True, forwarded_allow_ips=settings.trusted_proxies)
    else:
        kw.update(proxy_headers=False)
    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level=settings.log_level,
                server_header=False, date_header=True, **kw)


def reset_password(email: str) -> None:
    from sqlalchemy import delete, select

    from . import db
    from .models import User, UserSession
    from .security import hash_password, password_problem

    db.init_engine()
    db.run_migrations()
    s = db.SessionLocal()
    u = s.scalar(select(User).where(User.email == email.strip().lower()))
    if not u:
        sys.exit(f"No account with the email {email}.")
    pw = getpass.getpass("New password: ")
    if prob := password_problem(pw):
        sys.exit(prob)
    if getpass.getpass("Type it again: ") != pw:
        sys.exit("The passwords don't match.")
    u.password_hash = hash_password(pw)
    u.active = True
    s.execute(delete(UserSession).where(UserSession.user_id == u.id))
    from .services import seclog
    seclog.record(s, "user.update", "command line", ip="", detail=f"{u.email}: password reset from the server")
    s.commit()
    print(f"Password updated for {u.email}. The account is active.")


def reset_mfa(email: str) -> None:
    from sqlalchemy import delete, select

    from . import db
    from .models import User, UserSession
    from .services import seclog

    db.init_engine()
    db.run_migrations()
    s = db.SessionLocal()
    u = s.scalar(select(User).where(User.email == email.strip().lower()))
    if not u:
        sys.exit(f"No account with the email {email}.")
    u.mfa_secret, u.mfa_pending_secret, u.mfa_last_step = None, None, 0
    s.execute(delete(UserSession).where(UserSession.user_id == u.id))
    seclog.record(s, "user.update", "command line", ip="", detail=f"{u.email}: authenticator reset from the server")
    s.commit()
    print(f"Authenticator removed for {u.email}. They set up a new one at their next sign-in if it is required.")


if __name__ == "__main__":
    main()

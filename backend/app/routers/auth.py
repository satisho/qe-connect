"""Sign-in (with authenticator codes), first-run setup, sign-out, password and MFA changes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import APP_VERSION
from ..db import get_db
from ..models import User, UserSession
from ..security import (COOKIE, clear_session_cookie, current_user, find_session, hash_password, new_session,
                        password_problem, set_session_cookie, token_hash, verify_password)
from ..services import seclog, store, totp
from ..services.mail import email_ok

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "active": u.active,
            "mfa_enabled": bool(u.mfa_secret),
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}


class SetupIn(BaseModel):
    name: str
    email: str
    password: str
    organization: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class PasswordIn(BaseModel):
    current: str
    new: str


class CodeIn(BaseModel):
    code: str


class DisableIn(BaseModel):
    password: str


def policy(db: Session) -> dict:
    return store.get(db, "security")


@router.get("/state")
def state(request: Request, db: Session = Depends(get_db)):
    needs_setup = (db.scalar(select(func.count(User.id))) or 0) == 0
    s = find_session(request, db)
    user = s.user if s and s.mfa_state == "ok" else None
    pending = {"step": s.mfa_state, "email": s.user.email} if s and s.mfa_state != "ok" else None
    return {"needs_setup": needs_setup, "user": user_out(user) if user else None, "pending": pending,
            "version": APP_VERSION, "campaign": store.get(db, "campaign")["name"],
            "organization": store.org(db),
            "mfa_required": bool(policy(db).get("mfa_required")),
            "notice": getattr(request.state, "session_end", None)}


@router.post("/setup")
def setup(body: SetupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(409, "QE Connect is already set up. Sign in instead.")
    email = body.email.strip().lower()
    if not email_ok(email):
        raise HTTPException(422, "Enter a valid email address.")
    if p := password_problem(body.password):
        raise HTTPException(422, p)
    u = User(email=email, name=body.name.strip()[:120] or email, password_hash=hash_password(body.password), role="admin")
    db.add(u)
    db.flush()
    if org_name := " ".join(body.organization.split())[:120]:
        store.put(db, "organization", {"name": org_name})
    store.log(db, email, "user.setup", "Created the first administrator")
    seclog.record(db, "user.create", email, request, detail="First administrator created at setup")
    seclog.record(db, "signin", email, request)
    token = new_session(db, u)
    set_session_cookie(response, request, token)
    return {"user": user_out(u)}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()[:254]
    ip = seclog.client_ip(request)
    if seclog.signin_blocked(db, email, ip):
        seclog.record(db, "signin", email, request, "blocked", "Too many failed attempts")
        db.commit()
        raise HTTPException(429, "Too many failed sign-ins. Wait 15 minutes and try again.")
    u = db.scalar(select(User).where(User.email == email))
    if not u or not u.active or not verify_password(body.password, u.password_hash):
        reason = "unknown account" if not u else "account deactivated" if not u.active else "wrong password"
        seclog.record(db, "signin", email, request, "fail", reason)
        db.commit()
        raise HTTPException(401, "That email and password don't match an active account.")
    step = "verify" if u.mfa_secret else "setup" if policy(db).get("mfa_required") else "ok"
    token = new_session(db, u, step)
    if step == "ok":
        seclog.record(db, "signin", email, request)
        store.log(db, u.email, "user.login", "")
    else:
        seclog.record(db, "signin.password", email, request, detail="Password accepted; authenticator code " +
                      ("required" if step == "verify" else "setup required"))
    db.commit()
    set_session_cookie(response, request, token)
    return {"user": user_out(u) if step == "ok" else None, "pending": None if step == "ok" else {"step": step, "email": u.email}}


def _pending(request: Request, db: Session, *steps: str) -> UserSession:
    s = find_session(request, db)
    if not s or s.mfa_state not in steps:
        raise HTTPException(401, "Your sign-in has timed out. Sign in again.")
    return s


@router.post("/mfa/verify")
def mfa_verify(body: CodeIn, request: Request, db: Session = Depends(get_db)):
    s = _pending(request, db, "verify")
    u = s.user
    if seclog.signin_blocked(db, u.email, seclog.client_ip(request)):
        seclog.record(db, "mfa.verify", u.email, request, "blocked")
        db.commit()
        raise HTTPException(429, "Too many failed attempts. Wait 15 minutes and try again.")
    step = totp.verify(u.mfa_secret or "", body.code, u.mfa_last_step or 0)
    if step is None:
        seclog.record(db, "mfa.verify", u.email, request, "fail", "Wrong or reused code")
        db.commit()
        raise HTTPException(401, "That code isn't right. Check your authenticator app and try the newest code.")
    u.mfa_last_step = step
    _upgrade(db, s, request)
    return {"user": user_out(u)}


def _upgrade(db: Session, s: UserSession, request: Request) -> None:
    from datetime import timedelta

    from ..config import settings
    from ..models import utcnow

    s.mfa_state = "ok"
    s.expires_at = utcnow() + timedelta(hours=settings.session_hours)
    s.last_seen_at = utcnow()
    s.user.last_login_at = utcnow()
    seclog.record(db, "signin", s.user.email, request, detail="With authenticator code")
    store.log(db, s.user.email, "user.login", "")
    db.commit()


@router.post("/mfa/setup/start")
def mfa_setup_start(request: Request, db: Session = Depends(get_db)):
    s = _pending(request, db, "setup", "ok")
    u = s.user
    if u.mfa_secret:
        raise HTTPException(409, "An authenticator app is already set up. Turn it off first to set up a new one.")
    u.mfa_pending_secret = totp.new_secret()
    db.commit()
    uri = totp.otpauth_uri(u.mfa_pending_secret, u.email)
    return {"secret": u.mfa_pending_secret, "uri": uri, "qr": totp.qr_svg_data_uri(uri)}


@router.post("/mfa/setup/confirm")
def mfa_setup_confirm(body: CodeIn, request: Request, db: Session = Depends(get_db)):
    s = _pending(request, db, "setup", "ok")
    u = s.user
    if not u.mfa_pending_secret:
        raise HTTPException(409, "Start the setup again.")
    step = totp.verify(u.mfa_pending_secret, body.code, 0)
    if step is None:
        seclog.record(db, "mfa.setup", u.email, request, "fail", "Wrong code during setup")
        db.commit()
        raise HTTPException(422, "That code isn't right. Make sure the app shows QE Connect and try the newest code.")
    u.mfa_secret, u.mfa_pending_secret, u.mfa_last_step = u.mfa_pending_secret, None, step
    seclog.record(db, "mfa.enable", u.email, request, detail="Authenticator app set up")
    store.log(db, u.email, "user.mfa", "Set up an authenticator app")
    if s.mfa_state != "ok":
        _upgrade(db, s, request)
    else:
        tok = token_hash(request.cookies.get(COOKIE, ""))
        db.execute(delete(UserSession).where(UserSession.user_id == u.id, UserSession.token_hash != tok))
        db.commit()
    return {"user": user_out(u)}


@router.post("/mfa/disable")
def mfa_disable(body: DisableIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if policy(db).get("mfa_required"):
        raise HTTPException(409, "Your administrator requires an authenticator app for everyone.")
    if not verify_password(body.password, user.password_hash):
        seclog.record(db, "mfa.disable", user.email, request, "fail", "Wrong password")
        db.commit()
        raise HTTPException(400, "Your password isn't right.")
    user.mfa_secret, user.mfa_pending_secret, user.mfa_last_step = None, None, 0
    seclog.record(db, "mfa.disable", user.email, request, detail="Turned off own authenticator app")
    db.commit()
    return {"user": user_out(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    tok = request.cookies.get(COOKIE)
    if tok:
        s = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(tok)))
        if s:
            seclog.record(db, "signout", s.user.email, request)
            db.delete(s)
            db.commit()
    clear_session_cookie(response, request)
    return {"ok": True}


@router.post("/password")
def change_password(body: PasswordIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not verify_password(body.current, user.password_hash):
        seclog.record(db, "password.change", user.email, request, "fail", "Wrong current password")
        db.commit()
        raise HTTPException(400, "Your current password isn't right.")
    if p := password_problem(body.new):
        raise HTTPException(422, p)
    user.password_hash = hash_password(body.new)
    tok = token_hash(request.cookies.get(COOKIE, ""))
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.token_hash != tok))
    store.log(db, user.email, "user.password", "Changed own password")
    seclog.record(db, "password.change", user.email, request)
    db.commit()
    return {"ok": True}

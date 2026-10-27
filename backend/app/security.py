"""Passwords, sessions (idle timeout and MFA state), roles and request checks."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, UserSession, utcnow
from .services import seclog, store

COOKIE = "qec_session"
ROLES = ("viewer", "editor", "admin")
_N, _R, _P = 2**14, 8, 1
TOUCH_SECONDS = 60


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:
        return False


def password_problem(pw: str) -> str | None:
    if len(pw) < 10:
        return "Use at least 10 characters."
    if pw.lower() == pw or pw.upper() == pw or not any(c.isdigit() for c in pw):
        return "Mix upper and lower case letters and at least one number."
    return None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(db: Session, user: User, mfa_state: str = "ok") -> str:
    token = secrets.token_urlsafe(32)
    db.execute(delete(UserSession).where(UserSession.expires_at < utcnow()))
    now = utcnow()
    db.add(UserSession(token_hash=token_hash(token), user_id=user.id, mfa_state=mfa_state, last_seen_at=now,
                       expires_at=now + timedelta(hours=settings.session_hours if mfa_state == "ok" else 0.25)))
    if mfa_state == "ok":
        user.last_login_at = now
    db.commit()
    return token


def cookie_secure(request: Request) -> bool:
    return settings.secure_cookies or request.url.scheme == "https"


def set_session_cookie(response, request: Request, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=settings.session_hours * 3600, httponly=True,
                        samesite="strict", secure=cookie_secure(request), path="/")


def clear_session_cookie(response, request: Request) -> None:
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict", secure=cookie_secure(request))


def find_session(request: Request, db: Session) -> UserSession | None:
    """The session behind the request's cookie, after expiry and idle checks (any MFA state)."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    s = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(token)))
    if not s or not s.user.active:
        return None
    now = utcnow()
    if s.expires_at < now:
        db.delete(s)
        db.commit()
        return None
    idle = int(store.get(db, "security").get("idle_minutes") or 0)
    if idle and s.mfa_state == "ok" and (now - (s.last_seen_at or s.created_at)) > timedelta(minutes=idle):
        seclog.record(db, "session.idle", s.user.email, request, detail=f"Signed out after {idle} minutes without activity")
        db.delete(s)
        db.commit()
        request.state.session_end = f"You were signed out after {idle} minutes without activity. Sign in again."
        return None
    if (now - (s.last_seen_at or s.created_at)).total_seconds() > TOUCH_SECONDS:
        s.last_seen_at = now
        db.commit()
    return s


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    s = find_session(request, db)
    if not s or s.mfa_state != "ok":
        return None
    return s.user


def current_user(request: Request, user: User | None = Depends(current_user_optional)) -> User:
    if not user:
        raise HTTPException(401, getattr(request.state, "session_end", None) or "Sign in to continue.")
    return user


def require(role: str):
    level = ROLES.index(role)

    def dep(user: User = Depends(current_user)) -> User:
        if ROLES.index(user.role) < level:
            raise HTTPException(403, f"This needs the {role} role.")
        return user

    return dep


can_view = require("viewer")
can_edit = require("editor")
is_admin = require("admin")

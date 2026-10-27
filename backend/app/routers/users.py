"""Team accounts (administrators only)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, UserSession
from ..security import ROLES, hash_password, is_admin, password_problem
from ..services import seclog, store
from ..services.mail import email_ok
from .auth import user_out

router = APIRouter(prefix="/api/users", tags=["users"])


class UserIn(BaseModel):
    name: str = ""
    email: str
    role: str = "editor"
    password: str


class UserPatch(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None
    reset_mfa: Optional[bool] = None


def _admins(db: Session) -> int:
    return db.scalar(select(func.count(User.id)).where(User.role == "admin", User.active.is_(True))) or 0


@router.get("")
def list_users(db: Session = Depends(get_db), _: User = Depends(is_admin)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.name))]


@router.post("")
def create_user(body: UserIn, request: Request, db: Session = Depends(get_db), me: User = Depends(is_admin)):
    email = body.email.strip().lower()
    if not email_ok(email):
        raise HTTPException(422, "Enter a valid email address.")
    if body.role not in ROLES:
        raise HTTPException(422, "Role must be admin, editor or viewer.")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Someone already has an account with that email.")
    if p := password_problem(body.password):
        raise HTTPException(422, p)
    u = User(email=email, name=body.name.strip()[:120] or email, role=body.role, password_hash=hash_password(body.password))
    db.add(u)
    store.log(db, me.email, "user.create", f"Added {email} as {body.role}")
    seclog.record(db, "user.create", me.email, request, detail=f"Added {email} as {body.role}")
    db.commit()
    return user_out(u)


@router.patch("/{uid}")
def update_user(uid: int, body: UserPatch, request: Request, db: Session = Depends(get_db), me: User = Depends(is_admin)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "No such account.")
    changes = []
    if body.role is not None and body.role != u.role:
        if body.role not in ROLES:
            raise HTTPException(422, "Role must be admin, editor or viewer.")
        if u.role == "admin" and _admins(db) <= 1:
            raise HTTPException(409, "Keep at least one active administrator.")
        u.role = body.role
        changes.append(f"role {body.role}")
    if body.active is not None and body.active != u.active:
        if not body.active and u.role == "admin" and _admins(db) <= 1:
            raise HTTPException(409, "Keep at least one active administrator.")
        u.active = body.active
        if not body.active:
            db.execute(delete(UserSession).where(UserSession.user_id == u.id))
        changes.append("activated" if body.active else "deactivated")
    if body.name is not None:
        u.name = body.name.strip()[:120] or u.email
    if body.password:
        if p := password_problem(body.password):
            raise HTTPException(422, p)
        u.password_hash = hash_password(body.password)
        db.execute(delete(UserSession).where(UserSession.user_id == u.id))
        changes.append("password reset")
    if body.reset_mfa and u.mfa_secret:
        u.mfa_secret, u.mfa_pending_secret, u.mfa_last_step = None, None, 0
        db.execute(delete(UserSession).where(UserSession.user_id == u.id))
        changes.append("authenticator reset")
    store.log(db, me.email, "user.update", f"{u.email}: {', '.join(changes) or 'details'}")
    if changes:
        seclog.record(db, "user.update", me.email, request, detail=f"{u.email}: {', '.join(changes)}")
    db.commit()
    return user_out(u)


@router.delete("/{uid}")
def delete_user(uid: int, request: Request, db: Session = Depends(get_db), me: User = Depends(is_admin)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "No such account.")
    if u.id == me.id:
        raise HTTPException(409, "You can't remove your own account.")
    if u.role == "admin" and _admins(db) <= 1:
        raise HTTPException(409, "Keep at least one active administrator.")
    db.delete(u)
    store.log(db, me.email, "user.delete", f"Removed {u.email}")
    seclog.record(db, "user.delete", me.email, request, detail=f"Removed {u.email}")
    db.commit()
    return {"ok": True}

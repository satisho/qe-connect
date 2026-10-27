"""Sample data, password-protected workspace backups and the health check."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import APP_VERSION
from ..db import get_db
from ..models import User, utcnow
from ..security import is_admin, password_problem
from ..services import hosts, sample, seclog, store

router = APIRouter(prefix="/api", tags=["system"])
MAGIC = b"QECB1"
MAX_BACKUP = 50 * 1024 * 1024


def _key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)


def encrypt_backup(data: bytes, password: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt, nonce = os.urandom(16), os.urandom(12)
    return MAGIC + salt + nonce + AESGCM(_key(password, salt)).encrypt(nonce, data, MAGIC)


def decrypt_backup(blob: bytes, password: str) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt, nonce, ct = blob[5:21], blob[21:33], blob[33:]
    try:
        return AESGCM(_key(password, salt)).decrypt(nonce, ct, MAGIC)
    except InvalidTag as exc:
        raise HTTPException(422, "That password doesn't open this backup.") from exc


class BackupIn(BaseModel):
    password: str


@router.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@router.post("/sample")
def load_sample(db: Session = Depends(get_db), me: User = Depends(is_admin)):
    seclog.record(db, "delete.all", me.email, detail="Replaced all survey data with sample data")
    db.commit()
    sample.load(db, me.email)
    return {"ok": True}


@router.post("/workspace/export")
def export_workspace(body: BackupIn, request: Request, db: Session = Depends(get_db), me: User = Depends(is_admin)):
    if p := password_problem(body.password):
        raise HTTPException(422, f"Choose a stronger backup password. {p}")
    raw = json.dumps(sample.export_workspace(db), ensure_ascii=False).encode()
    blob = encrypt_backup(raw, body.password)
    store.log(db, me.email, "workspace.export", "Downloaded a password-protected backup")
    seclog.record(db, "export.backup", me.email, request, detail=f"Encrypted backup, {len(blob)} bytes")
    db.commit()
    return Response(blob, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="QE_Connect_backup_{utcnow():%Y-%m-%d}.qecbackup"'})


@router.post("/workspace/import")
async def import_workspace(request: Request, file: UploadFile = File(...), password: Optional[str] = Form(None),
                           db: Session = Depends(get_db), me: User = Depends(is_admin)):
    raw = await file.read(MAX_BACKUP + 1)
    if len(raw) > MAX_BACKUP:
        raise HTTPException(413, "That backup is larger than 50 MB.")
    if raw.startswith(MAGIC):
        if not password:
            raise HTTPException(422, "Enter the password this backup was protected with.")
        raw = decrypt_backup(raw, password)
    try:
        data = json.loads(raw.decode("utf-8-sig"))
        seclog.record(db, "delete.all", me.email, request, detail=f"Replaced all survey data from backup {file.filename}")
        res = sample.import_workspace(db, data, me.email)
        hosts.refresh(store.get(db, "delivery").get("link_base", ""))
        return res
    except (ValueError, KeyError, TypeError) as exc:
        db.rollback()
        raise HTTPException(422, f"This backup couldn't be restored: {exc}") from exc

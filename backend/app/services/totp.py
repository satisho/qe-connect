"""Authenticator-app codes (TOTP, RFC 6238) using only the standard library; QR codes drawn with segno."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    s = secret.upper().replace(" ", "")
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret: str, step: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    num = (struct.unpack(">I", digest[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(num).zfill(DIGITS)


def verify(secret: str, code: str, last_step: int = 0, now: float | None = None) -> int | None:
    """Return the matched time step, or None. Accepts one step either side; never a step at or before last_step."""
    code = "".join(c for c in (code or "") if c.isdigit())
    if len(code) != DIGITS or not secret:
        return None
    cur = int((now if now is not None else time.time()) // STEP)
    for step in (cur - 1, cur, cur + 1):
        if step > last_step and hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def otpauth_uri(secret: str, account: str, issuer: str = "QE Connect") -> str:
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP}")


def qr_svg_data_uri(uri: str) -> str:
    import segno

    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=5, border=2, dark="#0F2233", light="#FFFFFF", xmldecl=False)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()

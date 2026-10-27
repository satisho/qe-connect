"""Host names QE Connect answers to (protects a laptop install from DNS rebinding)."""
from __future__ import annotations

from urllib.parse import urlsplit

from ..config import settings

_dynamic: set[str] = set()


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def allowed() -> set[str]:
    base = {"localhost", "127.0.0.1", "::1", _host(settings.public_url)} | set(settings.allowed_hosts)
    return {h for h in base | _dynamic if h}


def refresh(link_base: str) -> None:
    """Also accept the host of the survey link address set on the Email delivery page."""
    _dynamic.clear()
    if h := _host(link_base or ""):
        _dynamic.add(h)


def ok(host_header: str) -> bool:
    hosts = allowed()
    if "*" in hosts:
        return True
    h = (host_header or "").strip().lower()
    if h.startswith("["):
        h = h[1:].split("]")[0]
    elif h.count(":") == 1:
        h = h.split(":")[0]
    return h in hosts

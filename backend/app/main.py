"""The QE Connect web application: API, request limits, security headers and the built web interface."""
from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager

os.environ.setdefault("OTEL_SDK_DISABLED", "true")  # no telemetry leaves the server

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

from . import db as dbmod  # noqa: E402
from .config import APP_VERSION, PROJECT_DIR, settings  # noqa: E402
from .routers import auth, public, security as security_router, settings as settings_router, setup, system, tracker, users  # noqa: E402
from .services import hosts, seclog, store  # noqa: E402
from .services.mail import MailWorker  # noqa: E402

log = logging.getLogger("qe_connect")
DIST = PROJECT_DIR / "frontend" / "dist"

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
PERMISSIONS = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"

# Request size limits (bytes): uploads get room for a 10 MB file, backups 50 MB, everything else 1 MB.
LIMIT_DEFAULT = 1 * 1024 * 1024
LIMITS = {"/api/applications/import": 11 * 1024 * 1024, "/api/questions/import": 11 * 1024 * 1024,
          "/api/lobs/import": 11 * 1024 * 1024, "/api/workspace/import": 51 * 1024 * 1024}

TOKEN_RE = re.compile(r"(/s/)[A-Za-z0-9_-]+")


class MaskSurveyLinks(logging.Filter):
    """Keep survey link tokens out of the access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(TOKEN_RE.sub(r"\1[link]", a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.msg, str):
            record.msg = TOKEN_RE.sub(r"\1[link]", record.msg)
        return True


def _json(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


class Guard:
    """Pure ASGI middleware: host check, body size limit, anti-forgery header, security headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        path, method = scope.get("path", ""), scope.get("method", "GET")
        https = scope.get("scheme") == "https"
        client = scope.get("client")
        token = seclog.CURRENT_IP.set(client[0] if client else "")

        async def send_headers(message):
            if message["type"] == "http.response.start":
                h = message.setdefault("headers", [])
                extra = {"content-security-policy": CSP, "x-content-type-options": "nosniff", "x-frame-options": "DENY",
                         "referrer-policy": "no-referrer", "cross-origin-opener-policy": "same-origin",
                         "permissions-policy": PERMISSIONS}
                if https:
                    extra["strict-transport-security"] = "max-age=31536000; includeSubDomains"
                if path.startswith("/api/"):
                    extra["cache-control"] = "no-store"
                names = {k.lower() for k, _ in h}
                for k, v in extra.items():
                    if k.encode() not in names:
                        h.append((k.encode(), v.encode()))
            await send(message)

        try:
            if not hosts.ok(headers.get("host", "")):
                return await _json(400, "QE Connect doesn't answer to this address. Add it to QEC_ALLOWED_HOSTS.")(scope, receive, send_headers)
            if path.startswith("/api/") and method not in ("GET", "HEAD", "OPTIONS") and headers.get("x-qec") != "1":
                return await _json(403, "Missing request header. Reload the page and try again.")(scope, receive, send_headers)
            limit = LIMITS.get(path, LIMIT_DEFAULT)
            try:
                if int(headers.get("content-length") or 0) > limit:
                    return await _json(413, "That request is too large.")(scope, receive, send_headers)
            except ValueError:
                return await _json(400, "Bad request.")(scope, receive, send_headers)
            if method in ("GET", "HEAD", "OPTIONS"):
                return await self.app(scope, receive, send_headers)
            # Read the body up to the limit before the app sees it, so an oversized request never reaches parsing.
            chunks, size, more = [], 0, True
            while more:
                message = await receive()
                if message["type"] != "http.request":
                    return  # client went away
                body = message.get("body", b"")
                size += len(body)
                if size > limit:
                    return await _json(413, "That request is too large.")(scope, receive, send_headers)
                chunks.append(body)
                more = message.get("more_body", False)
            replayed = False

            async def replay():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
                return await receive()

            await self.app(scope, replay, send_headers)
        finally:
            seclog.CURRENT_IP.reset(token)


def create_app(run_startup: bool = True) -> FastAPI:
    worker: MailWorker | None = None
    logging.getLogger("uvicorn.access").addFilter(MaskSurveyLinks())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        nonlocal worker
        if run_startup:
            dbmod.init_engine()
            dbmod.run_migrations()
            s = dbmod.SessionLocal()
            try:
                hosts.refresh(store.get(s, "delivery").get("link_base", ""))
            finally:
                s.close()
            if settings.mail_worker:
                worker = MailWorker(lambda: dbmod.SessionLocal())
                worker.start()
        yield
        if worker:
            worker.stop()

    app = FastAPI(title="QE Connect", version=APP_VERSION, lifespan=lifespan,
                  docs_url="/api/docs" if settings.api_docs else None, redoc_url=None,
                  openapi_url="/api/openapi.json" if settings.api_docs else None)

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "request"
        return JSONResponse({"detail": f"Check {field}: {first.get('msg', 'invalid value')}."}, status_code=422)

    for r in (auth.router, users.router, setup.router, settings_router.router, tracker.router, public.router,
              system.router, security_router.router):
        app.include_router(r)

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found."}, status_code=404)
        target = (DIST / path).resolve()
        if path and target.is_file() and DIST.resolve() in target.parents:
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith("assets/") else {}
            return FileResponse(target, headers=headers)
        index = DIST / "index.html"
        if not index.is_file():
            return JSONResponse({"detail": "The web interface hasn't been built. Run: cd frontend && npm install && npm run build"},
                                status_code=503)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return Guard(app)


app = create_app()
__all__ = ["app", "create_app"]

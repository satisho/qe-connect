"""Settings for QE Connect.

Every setting comes from an environment variable with the QEC_ prefix. A `.env`
file in the project root (the folder that holds start.bat) is read first, so
settings can live there instead of in the system environment. Every setting is
optional; the defaults run a single-user laptop install.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_VERSION = "1.0.1"

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=VALUE lines, # comments, optional quotes.

    Values already set in the real environment win over the file.
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _path(value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else (PROJECT_DIR / p).resolve()


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = field(default_factory=lambda: PROJECT_DIR / "data")
    database_url: str = ""
    public_url: str = ""
    session_hours: int = 12
    secure_cookies: bool = False
    api_docs: bool = False
    mail_client_secret: str = ""
    smtp_password: str = ""
    mail_cert_path: str = ""
    mail_worker: bool = True
    log_level: str = "info"
    tls_cert: str = ""
    tls_key: str = ""
    trusted_proxies: str = ""
    allowed_hosts: list = field(default_factory=list)

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "qe-connect.db"

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.sqlite_path.as_posix()}"

    @property
    def is_sqlite(self) -> bool:
        return self.db_url.startswith("sqlite")


def load_settings() -> Settings:
    _load_dotenv(PROJECT_DIR / ".env")
    e = os.environ.get
    port = _int("QEC_PORT", 8000)
    return Settings(
        host=e("QEC_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=port,
        data_dir=_path(e("QEC_DATA_DIR", "data").strip() or "data"),
        database_url=e("QEC_DATABASE_URL", "").strip(),
        public_url=(e("QEC_PUBLIC_URL", "").strip() or f"http://localhost:{port}").rstrip("/"),
        session_hours=max(1, _int("QEC_SESSION_HOURS", 12)),
        secure_cookies=_bool("QEC_SECURE_COOKIES", False),
        api_docs=_bool("QEC_API_DOCS", False),
        mail_client_secret=e("QEC_MAIL_CLIENT_SECRET", ""),
        smtp_password=e("QEC_SMTP_PASSWORD", ""),
        mail_cert_path=e("QEC_MAIL_CERT_PATH", "").strip(),
        mail_worker=_bool("QEC_MAIL_WORKER", True),
        log_level=(e("QEC_LOG_LEVEL", "info").strip() or "info").lower(),
        tls_cert=_path_or_blank(e("QEC_TLS_CERT", "")),
        tls_key=_path_or_blank(e("QEC_TLS_KEY", "")),
        trusted_proxies=e("QEC_TRUSTED_PROXIES", "").strip(),
        allowed_hosts=[h.strip().lower() for h in e("QEC_ALLOWED_HOSTS", "").split(",") if h.strip()],
    )


def _path_or_blank(v: str) -> str:
    v = v.strip()
    return str(_path(v)) if v else ""


settings = load_settings()

"""Application configuration and filesystem locations.

Keeping paths here prevents controllers and models from calculating their own
slightly different project roots. Every value can be overridden through an
environment variable for deployments and automated tests.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = PROJECT_ROOT.parent


def _environment_path(name: str, default: Path) -> Path:
    configured = os.environ.get(name)
    return Path(configured).expanduser().resolve() if configured else default.resolve()


CASE_ROOT = _environment_path(
    "CFD_CASE_ROOT",
    WORKSPACE_ROOT / "sprayDryer-6.0.0-onProduct-Trial02",
)
GRAPH_ROOT = _environment_path("CFD_GRAPH_ROOT", PROJECT_ROOT / "grafik" / "output")
REPORT_ROOT = _environment_path("CFD_REPORT_ROOT", PROJECT_ROOT / "report")
CASE_FILE_STATE_ROOT = _environment_path(
    "CFD_CASE_FILE_STATE_ROOT",
    PROJECT_ROOT / ".case_file_manager",
)
DATABASE_PATH = _environment_path(
    "CFD_DATABASE_PATH",
    PROJECT_ROOT / "instance" / "simulation_history.sqlite3",
)


def load_session_secret() -> str:
    """Load a stable production secret, with a local-development fallback."""

    configured_secret = os.environ.get("FLASK_SECRET_KEY", "").strip()
    if configured_secret:
        return configured_secret

    try:
        import fcntl
    except ImportError:  # Windows development environment
        return "maintenance-chamber-dev"

    secret_path = Path(
        os.environ.get("FLASK_SECRET_FILE", "/run/kmi-cfd-session-secret")
    )
    lock_path = secret_path.with_name(f"{secret_path.name}.lock")
    secret_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            if not secret_path.exists():
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(secret_path, flags, 0o600)
                try:
                    os.write(descriptor, secrets.token_urlsafe(64).encode("utf-8"))
                finally:
                    os.close(descriptor)

            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(secret_path, flags)
            try:
                secret = os.read(descriptor, 512).decode("utf-8").strip()
            finally:
                os.close(descriptor)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    if len(secret) < 32:
        raise RuntimeError("FLASK_SECRET_KEY/secret file minimal 32 karakter.")
    return secret


class AppConfig:
    """Default runtime configuration for the CFD web application."""

    SECRET_KEY = None
    LOGIN_USERNAME = os.environ.get("CFD_LOGIN_USERNAME", "kmi.cfd")
    LOGIN_PASSWORD = os.environ.get("CFD_LOGIN_PASSWORD", "kmi.cfd")

    PROJECT_ROOT = PROJECT_ROOT
    CASE_ROOT = CASE_ROOT
    GRAPH_OUTPUT_PATH = GRAPH_ROOT
    GRAPH_SCRIPT_PATH = PROJECT_ROOT / "grafik" / "2plot_residuals.py"
    GRAPH_LOG_PATH = CASE_ROOT / "log.run"
    REPORT_ROOT = REPORT_ROOT
    CASE_FILE_STATE_ROOT = CASE_FILE_STATE_ROOT
    DATABASE_PATH = DATABASE_PATH
    DECOMPOSE_PAR_DICT = CASE_ROOT / "system" / "decomposeParDict"

    DEFAULT_PROCESSOR_COUNT = 16
    MAX_PROCESSOR_COUNT = 32
    TRUST_PROXY_HEADERS = os.environ.get("TRUST_PROXY_HEADERS", "0") == "1"
    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Jakarta")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_COOKIE_SECURE", "0") == "1"

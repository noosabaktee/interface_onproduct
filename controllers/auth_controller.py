"""Authentication controller."""

from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from controllers.helpers import has_valid_form_csrf, has_valid_header_csrf


auth_bp = Blueprint("auth", __name__)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_ERROR_MESSAGE = "Token keamanan tidak valid atau sesi telah berganti. Muat ulang halaman lalu ulangi."
# Endpoint yang dipanggil melalui fetch dan selalu menjawab JSON.
JSON_ENDPOINTS = {
    "dashboard.start_terminal",
    "dashboard.cancel_terminal",
    "dashboard.stop_terminal",
    "dashboard.capture_report_screenshot",
    "dashboard.start_remote_paraview",
    "dashboard.stop_remote_paraview",
}


def get_safe_next(target: str | None) -> str:
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("dashboard.dashboard")


def _wants_json() -> bool:
    if request.endpoint in JSON_ENDPOINTS:
        return True
    if request.is_json or request.headers.get("X-CSRF-Token") is not None:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json"


def _same_origin_referrer_path() -> str | None:
    referrer = request.referrer
    if not referrer:
        return None
    parts = urlsplit(referrer)
    if parts.netloc and parts.netloc != request.host:
        return None
    path = parts.path or "/"
    return f"{path}?{parts.query}" if parts.query else path


def _csrf_failure():
    if _wants_json():
        return jsonify({"error": CSRF_ERROR_MESSAGE}), 403
    flash(CSRF_ERROR_MESSAGE, "danger")
    if request.endpoint == "auth.login":
        return redirect(url_for("auth.login"))
    return redirect(get_safe_next(_same_origin_referrer_path()))


@auth_bp.before_app_request
def require_login():
    if request.endpoint == "static":
        return None

    # Setiap sesi (termasuk sebelum login) memiliki token CSRF untuk form dan fetch.
    session.setdefault("csrf_token", secrets.token_urlsafe(32))

    # Semua request yang mengubah data wajib membawa token yang cocok, baik melalui
    # field form `csrf_token` maupun header `X-CSRF-Token`. Request ke route yang tidak
    # dikenal (endpoint None) dibiarkan berakhir 404/405 tanpa menyentuh data.
    if (
        request.method in UNSAFE_METHODS
        and request.endpoint is not None
        and not (has_valid_form_csrf() or has_valid_header_csrf())
    ):
        return _csrf_failure()

    if request.endpoint == "auth.login" or session.get("authenticated"):
        return None

    return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))


@auth_bp.app_context_processor
def inject_csrf_token():
    return {"csrf_token": lambda: session.get("csrf_token", "")}


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = get_safe_next(request.args.get("next") or request.form.get("next"))
    if session.get("authenticated"):
        return redirect(next_url)

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        expected_username = current_app.config["LOGIN_USERNAME"]
        expected_password = current_app.config["LOGIN_PASSWORD"]

        if hmac.compare_digest(username, expected_username) and hmac.compare_digest(
            password,
            expected_password,
        ):
            session.clear()
            session["authenticated"] = True
            session["username"] = username
            session["csrf_token"] = secrets.token_urlsafe(32)
            flash("Login berhasil. Selamat datang di CFD Workspace.", "success")
            return redirect(next_url)

        flash(
            "Invalid Username or Password. Gunakan username dan password yang sesuai.",
            "danger",
        )

    return render_template(
        "login.html",
        title="KMI - CFD Simulation Platform",
        next_url=next_url,
    )


@auth_bp.get("/logout")
def logout():
    session.clear()
    flash("Anda sudah logout.", "success")
    return redirect(url_for("auth.login"))


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
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from controllers.helpers import has_valid_form_csrf, has_valid_header_csrf


auth_bp = Blueprint("auth", __name__)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LOGIN_CSRF_COOKIE = "login_csrf"
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


def _valid_login_csrf() -> bool:
    supplied = request.form.get("csrf_token", "")
    expected = request.cookies.get(LOGIN_CSRF_COOKIE, "")
    return bool(supplied and expected and hmac.compare_digest(supplied, expected))


@auth_bp.before_app_request
def require_login():
    if request.endpoint == "static":
        return None

    # Form login dilindungi token double-submit pada cookie terpisah, sehingga pengunjung
    # yang belum login tidak pernah dibuatkan cookie session. Dengan begitu, request paralel
    # tanpa cookie tidak dapat menimpa cookie session hasil login.
    if request.endpoint == "auth.login":
        if request.method in UNSAFE_METHODS and not _valid_login_csrf():
            return _csrf_failure()
        return None

    # Pengunjung belum login hanya diarahkan ke halaman login tanpa menyentuh session.
    if not session.get("authenticated"):
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

    if "csrf_token" not in session:  # sesi lama sebelum token diperkenalkan
        session["csrf_token"] = secrets.token_urlsafe(32)

    # Semua request yang mengubah data wajib membawa token session yang cocok, baik melalui
    # field form `csrf_token` maupun header `X-CSRF-Token`. Request ke route yang tidak
    # dikenal (endpoint None) dibiarkan berakhir 404/405 tanpa menyentuh data.
    if (
        request.method in UNSAFE_METHODS
        and request.endpoint is not None
        and not (has_valid_form_csrf() or has_valid_header_csrf())
    ):
        return _csrf_failure()
    return None


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
            response = redirect(next_url)
            response.delete_cookie(LOGIN_CSRF_COOKIE, path=url_for("auth.login"))
            return response

        flash(
            "Invalid Username or Password. Gunakan username dan password yang sesuai.",
            "danger",
        )

    login_token = secrets.token_urlsafe(32)
    response = make_response(render_template(
        "login.html",
        title="KMI - CFD Simulation Platform",
        next_url=next_url,
        login_csrf_token=login_token,
    ))
    response.set_cookie(
        LOGIN_CSRF_COOKIE,
        login_token,
        max_age=3600,
        path=url_for("auth.login"),
        httponly=True,
        samesite="Lax",
        secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
    )
    return response


@auth_bp.get("/logout")
def logout():
    session.clear()
    flash("Anda sudah logout.", "success")
    return redirect(url_for("auth.login"))


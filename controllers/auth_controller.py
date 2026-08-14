"""Authentication controller."""

from __future__ import annotations

import hmac
import secrets

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)


auth_bp = Blueprint("auth", __name__)


def get_safe_next(target: str | None) -> str:
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("dashboard.dashboard")


@auth_bp.before_app_request
def require_login():
    if request.endpoint in {"auth.login", "static"}:
        return None

    if session.get("authenticated"):
        session.setdefault("csrf_token", secrets.token_urlsafe(32))
        return None

    return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))


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


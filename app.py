import hmac
import os
import secrets
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for

from controllers.dashboard_controller import dashboard_bp

LOGIN_USERNAME = os.environ.get("CFD_LOGIN_USERNAME", "kmi.cfd")
LOGIN_PASSWORD = os.environ.get("CFD_LOGIN_PASSWORD", "kmi.cfd")


def _load_session_secret():
    configured_secret = os.environ.get("FLASK_SECRET_KEY", "").strip()
    if configured_secret:
        return configured_secret

    secret_path = Path(os.environ.get("FLASK_SECRET_FILE", "/run/kmi-cfd-session-secret"))
    lock_path = secret_path.with_name(f"{secret_path.name}.lock")
    secret_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    try:
        import fcntl
    except ImportError:
        return "maintenance-chamber-dev"

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


def get_safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("dashboard.dashboard")


def create_app():
    app = Flask(__name__)
    app.secret_key = _load_session_secret()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FLASK_COOKIE_SECURE", "0") == "1",
    )

    @app.before_request
    def require_login():
        allowed_endpoints = {"login", "static"}
        if request.endpoint in allowed_endpoints:
            return None

        if session.get("authenticated"):
            session.setdefault("csrf_token", secrets.token_urlsafe(32))
            return None

        return redirect(url_for("login", next=request.full_path.rstrip("?")))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("authenticated"):
            return redirect(request.args.get("next") or url_for("dashboard.dashboard"))

        next_url = get_safe_next(request.args.get("next") or request.form.get("next"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if hmac.compare_digest(username, LOGIN_USERNAME) and hmac.compare_digest(
                password,
                LOGIN_PASSWORD,
            ):
                session.clear()
                session["authenticated"] = True
                session["username"] = username
                session["csrf_token"] = secrets.token_urlsafe(32)
                flash("Login berhasil. Selamat datang di CFD Workspace.", "success")
                return redirect(next_url)

            flash("Invalid Username or Password. Gunakan username dan password yang sesuai.", "danger")

        return render_template("login.html", title="KMI - CFD Simulation Platform", next_url=next_url)

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Anda sudah logout.", "success")
        return redirect(url_for("login"))

    app.register_blueprint(dashboard_bp)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)

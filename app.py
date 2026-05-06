from flask import Flask, flash, redirect, render_template, request, session, url_for

from controllers.dashboard_controller import dashboard_bp

LOGIN_USERNAME = "kmi.cfd"
LOGIN_PASSWORD = "kmi.cfd"


def get_safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("dashboard.dashboard")


def create_app():
    app = Flask(__name__)
    app.secret_key = "maintenance-chamber-dev"

    @app.before_request
    def require_login():
        allowed_endpoints = {"login", "static"}
        if request.endpoint in allowed_endpoints:
            return None

        if session.get("authenticated"):
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

            if username == LOGIN_USERNAME and password == LOGIN_PASSWORD:
                session.clear()
                session["authenticated"] = True
                session["username"] = username
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

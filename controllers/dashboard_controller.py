"""Dashboard navigation controller."""

from flask import redirect, render_template, url_for

from controllers import dashboard_bp


@dashboard_bp.get("/")
def index():
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.get("/dashboard")
def dashboard():
    return render_template("dashboard.html", title="Dashboard")

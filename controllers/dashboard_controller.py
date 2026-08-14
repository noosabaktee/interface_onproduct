"""Dashboard navigation controller."""

from flask import redirect, render_template, url_for

from controllers import dashboard_bp
from services import get_simulation_history_service


@dashboard_bp.get("/")
def index():
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.get("/dashboard")
def dashboard():
    history = get_simulation_history_service().dashboard_data(history_limit=10)
    return render_template(
        "dashboard.html",
        title="Dashboard",
        dashboard=history,
    )

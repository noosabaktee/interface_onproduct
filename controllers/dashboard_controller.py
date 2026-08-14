"""Dashboard navigation controller."""

from flask import redirect, render_template, request, url_for

from controllers import dashboard_bp
from services import get_simulation_history_service


@dashboard_bp.get("/")
def index():
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.get("/dashboard")
def dashboard():
    history_filter = request.args.get("history_type", "all").strip().lower()
    if history_filter not in {"all", "meshing", "solver"}:
        history_filter = "all"
    history = get_simulation_history_service().dashboard_data(
        history_limit=10,
        task_filter=None if history_filter == "all" else history_filter,
    )
    return render_template(
        "dashboard.html",
        title="Dashboard",
        dashboard=history,
    )

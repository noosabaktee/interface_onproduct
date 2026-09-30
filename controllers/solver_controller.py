"""Solver page controller."""

from flask import render_template

from controllers import dashboard_bp
from models.terminal_runner import is_meshing_ready


@dashboard_bp.get("/solver")
def solver():
    return render_template(
        "solver.html",
        title="Solver",
        meshing_ready=is_meshing_ready(),
    )

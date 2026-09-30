"""Meshing page controller."""

from flask import render_template

from controllers import dashboard_bp


@dashboard_bp.get("/meshing")
def meshing():
    return render_template("meshing.html", title="Meshing")

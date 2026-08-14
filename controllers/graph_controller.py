"""Residual graph controller."""

from flask import abort, flash, redirect, render_template, send_file, url_for

from controllers import dashboard_bp
from services import get_graph_service


@dashboard_bp.get("/graph")
def graph():
    return render_template(
        "graph.html",
        title="Graph",
        images=get_graph_service().list_images(),
    )


@dashboard_bp.get("/graph/image/<path:filename>")
def graph_image(filename):
    file_path = get_graph_service().resolve_image(filename)
    if file_path is None:
        abort(404)
    return send_file(file_path, mimetype="image/png", conditional=True, max_age=0)


@dashboard_bp.post("/graph/update")
def update_graph():
    success, message = get_graph_service().update()
    flash(message, "success" if success else "danger")
    return redirect(url_for("dashboard.graph"))


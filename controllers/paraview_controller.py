"""Local and remote ParaView controller."""

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from controllers import dashboard_bp
from controllers.helpers import has_valid_header_csrf
from models.paraview_model import (
    get_internal_mesh_path,
    get_paraview_case,
    get_surface_path,
    launch_case_file,
)
from models.paraview_server import (
    get_connection_config,
    get_server_state,
    start_server,
    stop_server,
)
from models.report_model import latest_report


@dashboard_bp.get("/paraview")
def paraview():
    return render_template(
        "paraview.html",
        title="Paraview",
        case=get_paraview_case(),
        latest_report=latest_report(),
    )


@dashboard_bp.get("/paraview/remote")
def remote_paraview():
    return render_template(
        "remote_paraview.html",
        title="Remote ParaView",
        case=get_paraview_case(),
        remote_connection=get_connection_config(_request_connection_host()),
    )


@dashboard_bp.post("/paraview/open")
def open_paraview_case():
    success, message = launch_case_file()
    flash(message, "success" if success else "warning")
    return redirect(url_for("dashboard.paraview"))


@dashboard_bp.post("/paraview/remote/start")
def start_remote_paraview():
    csrf_error = _remote_csrf_error()
    if csrf_error:
        return csrf_error
    state = _remote_state_response(start_server())
    return jsonify(state), (503 if state.get("error") else 200)


@dashboard_bp.post("/paraview/remote/stop")
def stop_remote_paraview():
    csrf_error = _remote_csrf_error()
    if csrf_error:
        return csrf_error
    return jsonify(_remote_state_response(stop_server()))


@dashboard_bp.get("/paraview/remote/status")
def remote_paraview_status():
    return jsonify(_remote_state_response(get_server_state()))


@dashboard_bp.get("/paraview/surface/<surface_id>")
def paraview_surface(surface_id):
    surface_path = get_surface_path(surface_id)
    if surface_path is None:
        abort(404)
    return send_file(surface_path, mimetype="application/xml", conditional=True, max_age=0)


@dashboard_bp.get("/paraview/internal-mesh")
def paraview_internal_mesh():
    mesh_path = get_internal_mesh_path()
    if mesh_path is None:
        abort(404)
    return send_file(mesh_path, mimetype="application/xml", conditional=True, max_age=0)


def _request_connection_host() -> str:
    forwarded_host = ""
    if current_app.config["TRUST_PROXY_HEADERS"]:
        forwarded_host = request.headers.get("X-Forwarded-Host", "")
    return (forwarded_host.split(",", 1)[0] or request.host).strip()


def _remote_state_response(state: dict) -> dict:
    response = dict(state)
    response.update(get_connection_config(_request_connection_host()))
    return response


def _remote_csrf_error():
    if has_valid_header_csrf():
        return None
    return jsonify({"error": "Token keamanan tidak valid. Muat ulang halaman."}), 403

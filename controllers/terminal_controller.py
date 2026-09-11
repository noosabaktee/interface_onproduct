"""Case-root bounded web terminal controller."""

from flask import jsonify, render_template, request

from controllers import dashboard_bp
from models.sandbox_terminal import SandboxTerminalError
from services import get_sandbox_terminal


@dashboard_bp.get("/terminal")
def terminal():
    state = get_sandbox_terminal().snapshot()
    return render_template(
        "terminal.html",
        title="Terminal",
        terminal_state=state,
    )


@dashboard_bp.get("/terminal/status")
def terminal_status():
    return jsonify(get_sandbox_terminal().snapshot())


@dashboard_bp.post("/terminal/run")
def terminal_run():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(get_sandbox_terminal().start(payload.get("command", "")))
    except SandboxTerminalError as exc:
        state = get_sandbox_terminal().snapshot()
        state["error"] = str(exc)
        return jsonify(state), 400


@dashboard_bp.post("/terminal/stop")
def terminal_stop():
    try:
        return jsonify(get_sandbox_terminal().stop())
    except SandboxTerminalError as exc:
        state = get_sandbox_terminal().snapshot()
        state["error"] = str(exc)
        return jsonify(state), 400

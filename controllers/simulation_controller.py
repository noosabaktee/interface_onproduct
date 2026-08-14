"""Meshing and solver execution controller."""

import io

from flask import abort, jsonify, render_template, send_file

from controllers import dashboard_bp
from models.terminal_runner import (
    cancel_command,
    get_command_state,
    is_meshing_ready,
    start_command,
    stop_command,
)
from services import get_simulation_history_service


SUPPORTED_TASKS = {"meshing", "solver"}


@dashboard_bp.get("/meshing")
def meshing():
    return render_template(
        "progress.html",
        title="Meshing",
        progress_title="Meshing Progress",
        progress_value=35,
        status_label="Preparing mesh dictionaries and block generation...",
        task_key="meshing",
        action_label="Execute Meshing",
    )


@dashboard_bp.get("/solver")
def solver():
    return render_template(
        "progress.html",
        title="Solver",
        progress_title="Solver Progress",
        progress_value=12,
        status_label="Waiting for processor setup and initial fields...",
        task_key="solver",
        action_label="Execute Solver",
        meshing_ready=is_meshing_ready(),
    )


@dashboard_bp.post("/terminal/<task_key>/start")
def start_terminal(task_key):
    task_error = _unsupported_task_error(task_key)
    if task_error:
        return task_error
    return jsonify(start_command(task_key, get_simulation_history_service()))


@dashboard_bp.post("/terminal/<task_key>/cancel")
def cancel_terminal(task_key):
    task_error = _unsupported_task_error(task_key)
    if task_error:
        return task_error
    if not cancel_command(task_key):
        return jsonify({"error": f"{task_key.capitalize()} is not running."}), 400

    state = get_command_state(task_key)
    state["message"] = f"{task_key.capitalize()} cancelled."
    return jsonify(state)


@dashboard_bp.post("/terminal/<task_key>/stop")
def stop_terminal(task_key):
    task_error = _unsupported_task_error(task_key)
    if task_error:
        return task_error
    if not stop_command(task_key):
        return jsonify({"error": f"{task_key.capitalize()} is not running."}), 400

    state = get_command_state(task_key)
    state["message"] = f"{task_key.capitalize()} stopped."
    return jsonify(state)


@dashboard_bp.get("/terminal/<task_key>/logs")
def terminal_logs(task_key):
    task_error = _unsupported_task_error(task_key)
    if task_error:
        return task_error
    return jsonify(get_command_state(task_key))


@dashboard_bp.get("/terminal/<task_key>/download-logs")
def download_terminal_logs(task_key):
    if task_key not in SUPPORTED_TASKS:
        abort(404)
    state = get_command_state(task_key)
    if not state["lines"]:
        abort(404)

    buffer = io.BytesIO("\n".join(state["lines"]).encode("utf-8"))
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{task_key}_log.txt",
        mimetype="text/plain",
    )


def _unsupported_task_error(task_key: str):
    if task_key in SUPPORTED_TASKS:
        return None
    return jsonify({"error": "Task tidak dikenal."}), 404

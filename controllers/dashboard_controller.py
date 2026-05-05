from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from models.parameter_model import load_parameter_groups
from models.terminal_runner import get_command_state, start_command


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.route("/dashboard")
def dashboard():
    return render_template(
        "dashboard.html",
        title="Dashboard",
    )


@dashboard_bp.route("/input-parameter")
def input_parameter():
    groups = load_parameter_groups()
    return render_template(
        "input_parameter.html",
        groups=groups,
        title="Input Parameter",
        active_group_key="1",
    )


@dashboard_bp.route("/set-processor", methods=["GET", "POST"])
def set_processor():
    processor_count = 4
    if request.method == "POST":
        try:
            processor_count = int(request.form.get("processor_count", processor_count))
        except ValueError:
            processor_count = 4

        processor_count = max(1, min(processor_count, 16))
        flash(f"Jumlah processor diset ke {processor_count}.", "success")

    return render_template(
        "set_processor.html",
        processor_count=processor_count,
        title="Set Processor",
    )


@dashboard_bp.route("/meshing")
def meshing():
    return render_template(
        "progress.html",
        title="Meshing",
        progress_title="Meshing Progress",
        progress_value=35,
        status_label="Preparing mesh dictionaries",
        task_key="meshing",
        action_label="Jalankan Meshing",
    )


@dashboard_bp.route("/solver")
def solver():
    return render_template(
        "progress.html",
        title="Solver",
        progress_title="Solver Progress",
        progress_value=12,
        status_label="Waiting for processor setup",
        task_key="solver",
        action_label="Jalankan Solver",
    )


@dashboard_bp.post("/terminal/<task_key>/start")
def start_terminal(task_key):
    if task_key not in {"meshing", "solver"}:
        return jsonify({"error": "Task tidak dikenal."}), 404

    state = start_command(task_key)
    return jsonify(state)


@dashboard_bp.get("/terminal/<task_key>/logs")
def terminal_logs(task_key):
    if task_key not in {"meshing", "solver"}:
        return jsonify({"error": "Task tidak dikenal."}), 404

    return jsonify(get_command_state(task_key))


@dashboard_bp.route("/paraview")
def paraview():
    return render_template(
        "paraview.html",
        title="Paraview",
    )


@dashboard_bp.route("/graph")
def graph():
    return render_template(
        "graph.html",
        title="Graph",
        matplotlib_ready=False,
    )


@dashboard_bp.route("/report")
def report():
    return render_template(
        "simple_page.html",
        title="Report",
        page_title="Report",
        page_text="Area ini disiapkan untuk rangkuman parameter, status simulasi, dan hasil validasi.",
    )

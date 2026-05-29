from pathlib import Path
import subprocess
import sys
import io

from flask import abort, Blueprint, flash, jsonify, redirect, render_template, request, send_file, url_for

from models.parameter_model import (
    IGNORED_FIELD_NAMES,
    PRODUCT_LABELS,
    load_parameter_groups,
    save_parameter_values,
)
from models.paraview_model import get_internal_mesh_path, get_paraview_case, get_surface_path, launch_case_file
from models.report_model import (
    build_report_pdf,
    create_report,
    delete_report,
    get_report,
    list_reports,
    latest_report,
    save_capture,
)
from models.terminal_runner import cancel_command, get_command_state, is_meshing_ready, start_command, stop_command

dashboard_bp = Blueprint("dashboard", __name__)

APP_ROOT = Path(__file__).resolve().parents[1]
GRAFIK_OUTPUT_PATH = APP_ROOT / "grafik" / "output"
GRAFIK_SCRIPT = APP_ROOT / "grafik" / "2plot_residuals.py"
GRAFIK_LOG_RUN = APP_ROOT.parent / "sprayDryer-6.0.0-onProduct-Trial02" / "log.run"
DECOMPOSE_PAR_DICT = APP_ROOT.parent / "sprayDryer-6.0.0-onProduct-Trial02" / "system" / "decomposeParDict"


def _load_number_of_subdomains(default=16):
    if not DECOMPOSE_PAR_DICT.exists():
        return default

    try:
        for line in DECOMPOSE_PAR_DICT.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("numberOfSubdomains"):
                parts = stripped.rstrip(";").split()
                if len(parts) >= 2:
                    return int(parts[1])
    except (OSError, ValueError):
        pass

    return default


def _save_number_of_subdomains(value):
    if not DECOMPOSE_PAR_DICT.exists():
        return False

    try:
        text = DECOMPOSE_PAR_DICT.read_text(encoding="utf-8").splitlines()
        updated = False
        new_lines = []

        for line in text:
            stripped = line.strip()
            if stripped.startswith("numberOfSubdomains"):
                indent = line[: len(line) - len(line.lstrip())]
                new_lines.append(f"{indent}numberOfSubdomains {value};")
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            insert_idx = next(
                (idx for idx, line in enumerate(new_lines) if line.strip().startswith("method")),
                len(new_lines),
            )
            new_lines.insert(insert_idx, f"numberOfSubdomains {value};")

        DECOMPOSE_PAR_DICT.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


@dashboard_bp.route("/")
def index():
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.route("/dashboard")
def dashboard():
    return render_template(
        "dashboard.html",
        title="Dashboard",
    )


@dashboard_bp.route("/input-parameter", methods=["GET", "POST"])
def input_parameter():
    parameter_mode = request.values.get("parameter_mode", "developer")
    if parameter_mode not in {"developer", "production"}:
        parameter_mode = "developer"
    selected_product = request.values.get("product", "ckr")
    if selected_product not in PRODUCT_LABELS:
        selected_product = "ckr"
    active_group_key = request.form.get("active_group_key", "0")
    if request.method == "POST":
        updated, skipped = save_parameter_values(
            request.form,
            active_group_key,
            parameter_mode,
            selected_product,
        )
        if updated:
            flash(f"{updated} parameter berhasil disimpan ke file case.", "success")
        else:
            flash("Tidak ada parameter yang berubah. Cek input atau location yang belum didukung.", "warning")
        if skipped:
            flash("Location belum diproses untuk: " + ", ".join(skipped), "warning")

    groups = load_parameter_groups(parameter_mode, selected_product)
    return render_template(
        "input_parameter.html",
        groups=groups,
        title="Input Parameter",
        IGNORED_FIELD_NAMES=IGNORED_FIELD_NAMES,
        active_group_key=active_group_key,
        parameter_mode=parameter_mode,
        selected_product=selected_product,
        product_labels=PRODUCT_LABELS,
    )


@dashboard_bp.route("/set-processor", methods=["GET", "POST"])
def set_processor():
    processor_count = _load_number_of_subdomains()
    if request.method == "POST":
        try:
            processor_count = int(request.form.get("processor_count", processor_count))
        except ValueError:
            processor_count = 16

        processor_count = max(1, min(processor_count, 16))
        if _save_number_of_subdomains(processor_count):
            flash(f"Jumlah processor diset ke {processor_count}. file decomposeParDict diperbarui.", "success")
        else:
            flash(
                "Gagal menyimpan jumlah processor ke decomposeParDict. Pastikan file tersedia dan dapat ditulis.",
                "danger",
            )

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
        status_label="Preparing mesh dictionaries and block generation...",
        task_key="meshing",
        action_label="Execute Meshing",
    )


@dashboard_bp.route("/solver")
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
    if task_key not in {"meshing", "solver"}:
        return jsonify({"error": "Task tidak dikenal."}), 404

    state = start_command(task_key)
    return jsonify(state)


@dashboard_bp.post("/terminal/<task_key>/cancel")
def cancel_terminal(task_key):
    if task_key not in {"meshing", "solver"}:
        return jsonify({"error": "Task tidak dikenal."}), 404

    if cancel_command(task_key):
        state = get_command_state(task_key)
        state["message"] = f"{task_key.capitalize()} cancelled."
        return jsonify(state)
    else:
        return jsonify({"error": f"{task_key.capitalize()} is not running."}), 400


@dashboard_bp.post("/terminal/<task_key>/stop")
def stop_terminal(task_key):
    if task_key not in {"meshing", "solver"}:
        return jsonify({"error": "Task tidak dikenal."}), 404

    if stop_command(task_key):
        state = get_command_state(task_key)
        state["message"] = f"{task_key.capitalize()} stopped."
        return jsonify(state)
    else:
        return jsonify({"error": f"{task_key.capitalize()} is not running."}), 400


@dashboard_bp.get("/terminal/<task_key>/logs")
def terminal_logs(task_key):
    if task_key not in {"meshing", "solver"}:
        return jsonify({"error": "Task tidak dikenal."}), 404

    return jsonify(get_command_state(task_key))


@dashboard_bp.get("/terminal/<task_key>/download-logs")
def download_terminal_logs(task_key):
    if task_key not in {"meshing", "solver"}:
        abort(404)

    state = get_command_state(task_key)
    if not state["lines"]:
        abort(404)

    log_content = "\n".join(state["lines"])
    buffer = io.BytesIO(log_content.encode("utf-8"))
    buffer.seek(0)

    filename = f"{task_key}_log.txt"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="text/plain",
    )


@dashboard_bp.route("/paraview")
def paraview():
    return render_template(
        "paraview.html",
        title="Paraview",
        case=get_paraview_case(),
        latest_report=latest_report(),
    )


@dashboard_bp.post("/paraview/open")
def open_paraview_case():
    success, message = launch_case_file()
    flash(message, "success" if success else "warning")
    return redirect(url_for("dashboard.paraview"))


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


def _list_graph_images():
    if not GRAFIK_OUTPUT_PATH.exists():
        return []
    return sorted([path.name for path in GRAFIK_OUTPUT_PATH.glob("*.png")])


def _run_graph_update():
    if not GRAFIK_SCRIPT.exists() or not GRAFIK_LOG_RUN.exists():
        return False, "File script atau log tidak ditemukan untuk pembaruan grafik."

    try:
        result = subprocess.run(
            [
                sys.executable,
                "grafik/2plot_residuals.py",
                "../sprayDryer-6.0.0-onProduct-Trial02/log.run",
                "--output",
                "grafik/output",
                "--linear",
                "--dpi",
                "150",
            ],
            cwd=APP_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except Exception as exc:
        return False, f"Gagal memperbarui grafik: {exc}"

    if result.returncode != 0:
        error_text = (result.stderr or result.stdout or "Unknown error").strip().splitlines()[-1]
        return False, f"Update grafik gagal: {error_text}"

    return True, "Grafik berhasil diperbarui."


@dashboard_bp.route("/graph")
def graph():
    return render_template(
        "graph.html",
        title="Graph",
        images=_list_graph_images(),
    )


@dashboard_bp.route("/graph/image/<path:filename>")
def graph_image(filename):
    file_path = GRAFIK_OUTPUT_PATH / filename
    try:
        resolved = file_path.resolve()
    except OSError:
        abort(404)

    if not resolved.is_file() or resolved.parent != GRAFIK_OUTPUT_PATH.resolve():
        abort(404)

    return send_file(resolved, mimetype="image/png", conditional=True, max_age=0)


@dashboard_bp.route("/graph/update", methods=["POST"])
def update_graph():
    success, message = _run_graph_update()
    flash(message, "success" if success else "danger")

    return redirect(url_for("dashboard.graph"))


@dashboard_bp.route("/report")
def report():
    reports = list_reports()
    return render_template(
        "report.html",
        title="Report",
        reports=reports,
        selected_report=reports[0] if reports else None,
        latest_report=reports[0] if reports else None,
    )


@dashboard_bp.route("/report/<report_name>")
def report_detail(report_name):
    selected_report = get_report(report_name)
    if selected_report is None:
        abort(404)

    return render_template(
        "report.html",
        title="Report",
        reports=list_reports(),
        selected_report=selected_report,
        latest_report=latest_report(),
    )


@dashboard_bp.post("/report/get")
def get_simulation_report():
    graph_success, graph_message = _run_graph_update()
    selected_report, copied_graphs = create_report(GRAFIK_OUTPUT_PATH)

    if graph_success:
        flash(f"Report {selected_report['name']} dibuat. {copied_graphs} grafik disimpan.", "success")
    else:
        flash(graph_message, "warning")
        flash(f"Report {selected_report['name']} dibuat dengan grafik yang tersedia.", "success")

    return redirect(url_for("dashboard.report_detail", report_name=selected_report["name"]))


@dashboard_bp.post("/report/<report_name>/delete")
def delete_simulation_report(report_name):
    if delete_report(report_name):
        flash(f"Report {report_name} berhasil dihapus.", "success")
    else:
        flash("Report tidak ditemukan atau tidak bisa dihapus.", "danger")
    return redirect(url_for("dashboard.report"))


@dashboard_bp.post("/report/capture")
def capture_report_screenshot():
    payload = request.get_json(silent=True) or {}
    try:
        report_item, filename = save_capture(
            payload.get("report_name"),
            payload.get("image"),
            payload.get("side"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "message": f"Capture {filename} tersimpan ke report {report_item['name']}.",
            "report_name": report_item["name"],
            "filename": filename,
        }
    )


@dashboard_bp.get("/report/file/<report_name>/<folder>/<path:filename>")
def report_file(report_name, folder, filename):
    selected_report = get_report(report_name)
    if selected_report is None or folder not in {"screenshots", "graphs"}:
        abort(404)

    file_path = selected_report["path"] / folder / filename
    try:
        resolved = file_path.resolve()
    except OSError:
        abort(404)

    allowed_parent = (selected_report["path"] / folder).resolve()
    if not resolved.is_file() or resolved.parent != allowed_parent:
        abort(404)

    return send_file(resolved, mimetype="image/png", conditional=True, max_age=0)


@dashboard_bp.get("/report/<report_name>/export-pdf")
def export_report_pdf(report_name):
    pdf_buffer = build_report_pdf(report_name)
    if pdf_buffer is None:
        abort(404)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"report_{report_name}.pdf",
        mimetype="application/pdf",
    )

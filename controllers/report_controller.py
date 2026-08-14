"""Simulation report controller."""

from flask import (
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from controllers import dashboard_bp
from models.report_model import (
    build_report_pdf,
    create_report,
    delete_report,
    get_report,
    latest_report,
    list_reports,
    save_capture,
)
from services import get_graph_service


@dashboard_bp.get("/report")
def report():
    reports = list_reports()
    selected_report = reports[0] if reports else None
    return render_template(
        "report.html",
        title="Report",
        reports=reports,
        selected_report=selected_report,
        latest_report=selected_report,
    )


@dashboard_bp.get("/report/<report_name>")
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
    graph_service = get_graph_service()
    graph_success, graph_message = graph_service.update()
    selected_report, copied_graphs = create_report(graph_service.output_path)

    if graph_success:
        flash(
            f"Report {selected_report['name']} dibuat. "
            f"{copied_graphs} grafik disimpan.",
            "success",
        )
    else:
        flash(graph_message, "warning")
        flash(
            f"Report {selected_report['name']} dibuat dengan grafik yang tersedia.",
            "success",
        )
    return redirect(
        url_for("dashboard.report_detail", report_name=selected_report["name"])
    )


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
            "message": (
                f"Capture {filename} tersimpan ke report {report_item['name']}."
            ),
            "report_name": report_item["name"],
            "filename": filename,
        }
    )


@dashboard_bp.get("/report/file/<report_name>/<folder>/<path:filename>")
def report_file(report_name, folder, filename):
    selected_report = get_report(report_name)
    if selected_report is None or folder not in {"screenshots", "graphs"}:
        abort(404)

    try:
        allowed_parent = (selected_report["path"] / folder).resolve()
        resolved = (allowed_parent / filename).resolve()
    except OSError:
        abort(404)
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

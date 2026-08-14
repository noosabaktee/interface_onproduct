"""Case-file management controller."""

import zipfile

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
from controllers.helpers import has_valid_form_csrf, send_temporary_archive
from models.case_file_manager import CaseFileError
from services import get_case_file_manager


@dashboard_bp.get("/case-files")
def case_file_manager():
    manager = get_case_file_manager()
    listing = manager.list_files(
        search=request.args.get("q", ""),
        category=request.args.get("type", "all"),
        page=request.args.get("page", 1),
    )
    return render_template(
        "case_file_manager.html",
        title="Case File Manager",
        case_root=manager.case_root,
        listing=listing,
    )


@dashboard_bp.get("/case-files/text/<path:relative_path>")
def get_case_text_file(relative_path):
    try:
        return jsonify(get_case_file_manager().read_text(relative_path))
    except CaseFileError as exc:
        return jsonify({"error": str(exc)}), 400


@dashboard_bp.post("/case-files/upload")
def upload_case_files():
    _require_form_csrf()
    try:
        result = get_case_file_manager().upload_files(
            request.files.getlist("files"),
            target_folder=request.form.get("target_folder", ""),
            replace=request.form.get("replace") == "1",
        )
        flash(
            f"Upload selesai: {result['added']} file baru dan "
            f"{result['replaced']} file diganti.",
            "success",
        )
    except CaseFileError as exc:
        flash(str(exc), "danger")
    return _manager_redirect()


@dashboard_bp.post("/case-files/replace/<path:relative_path>")
def replace_case_file(relative_path):
    _require_form_csrf()
    try:
        result = get_case_file_manager().replace_file(
            relative_path,
            request.files.get("file"),
        )
        flash(f"File {result['path']} berhasil diganti.", "success")
    except CaseFileError as exc:
        flash(str(exc), "danger")
    return _manager_redirect()


@dashboard_bp.post("/case-files/save/<path:relative_path>")
def save_case_text_file(relative_path):
    _require_form_csrf()
    try:
        get_case_file_manager().save_text(
            relative_path,
            request.form.get("content", ""),
        )
        flash(f"Perubahan {relative_path} berhasil disimpan.", "success")
    except CaseFileError as exc:
        flash(str(exc), "danger")
    return _manager_redirect()


@dashboard_bp.get("/case-files/download/<path:relative_path>")
def download_case_file(relative_path):
    try:
        path = get_case_file_manager().resolve_path(relative_path)
        if not path.is_file() or path.is_symlink():
            raise CaseFileError("Target bukan file biasa dan tidak dapat didownload.")
    except CaseFileError:
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name)


@dashboard_bp.post("/case-files/delete/<path:relative_path>")
def delete_case_file(relative_path):
    _require_form_csrf()
    try:
        deleted_path = get_case_file_manager().delete_file(relative_path)
        flash(f"File {deleted_path} berhasil dihapus.", "success")
    except CaseFileError as exc:
        flash(str(exc), "danger")
    return _manager_redirect()


@dashboard_bp.get("/case-files/download-all")
def download_all_case_files():
    manager = get_case_file_manager()
    try:
        archive_path, _ = manager.build_case_archive()
    except (CaseFileError, OSError, zipfile.BadZipFile) as exc:
        flash(f"ZIP case gagal dibuat: {exc}", "danger")
        return _manager_redirect()
    return send_temporary_archive(
        archive_path,
        f"{manager.case_root.name}-all-files.zip",
    )


@dashboard_bp.get("/case-files/download-logs")
def download_all_case_logs():
    manager = get_case_file_manager()
    try:
        archive_path, _ = manager.build_logs_archive()
    except (CaseFileError, OSError, zipfile.BadZipFile) as exc:
        flash(f"ZIP log gagal dibuat: {exc}", "danger")
        return _manager_redirect()
    return send_temporary_archive(archive_path, f"{manager.case_root.name}-logs.zip")


@dashboard_bp.post("/case-files/clear")
def clear_case_files():
    _require_form_csrf()
    if request.form.get("confirmation", "").strip().upper() != "CLEAR":
        flash("Konfirmasi tidak cocok. Ketik CLEAR untuk menjalankan operasi.", "danger")
        return _manager_redirect()

    mode = request.form.get("mode", "")
    labels = {
        "results": "hasil simulasi dan log",
        "logs": "file log",
        "uploads": "file upload yang tercatat",
        "reset": "hasil, log, dan upload case",
    }
    try:
        result = get_case_file_manager().clear(mode)
        flash(
            f"Pembersihan {labels.get(mode, mode)} selesai: "
            f"{result['files']} file dan {result['directories']} folder dihapus; "
            f"{result['restored']} file asli dipulihkan.",
            "success",
        )
    except (CaseFileError, OSError) as exc:
        flash(f"Pembersihan case gagal: {exc}", "danger")
    return _manager_redirect()


def _require_form_csrf() -> None:
    if not has_valid_form_csrf():
        abort(400, "Token keamanan tidak valid.")


def _manager_redirect():
    return redirect(url_for("dashboard.case_file_manager"))

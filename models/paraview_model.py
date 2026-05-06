import os
import re
import shutil
import subprocess
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = APP_ROOT.parent
CASE_DIR_NAME = "sprayDryer-6.0.0-onProduct-Trial02"
CASE_FILE_NAME = f"{CASE_DIR_NAME}.foam"
CASE_ROOT = WORKSPACE_ROOT / CASE_DIR_NAME
CASE_FILE = CASE_ROOT / CASE_FILE_NAME

SURFACE_ID_SEPARATOR = "--"


def get_paraview_case():
    case_exists = CASE_ROOT.exists()
    foam_exists = CASE_FILE.exists()
    time_directories = _time_directories(CASE_ROOT) if case_exists else []
    latest_time = time_directories[-1] if time_directories else None
    latest_fields = _field_names(CASE_ROOT / latest_time) if latest_time else []
    processors = _processor_directories(CASE_ROOT) if case_exists else []
    surfaces = _surface_files(CASE_ROOT) if case_exists else []
    default_surface = _default_surface(surfaces)

    return {
        "case_exists": case_exists,
        "foam_exists": foam_exists,
        "case_root": str(CASE_ROOT),
        "case_root_name": CASE_ROOT.name,
        "foam_path": str(CASE_FILE),
        "foam_name": CASE_FILE.name,
        "foam_size": _format_bytes(CASE_FILE.stat().st_size) if foam_exists else "-",
        "time_directories": time_directories,
        "latest_time": latest_time or "-",
        "latest_fields": latest_fields,
        "processors": processors,
        "surfaces": surfaces,
        "default_surface": default_surface,
        "paraview_command": _find_paraview_command(),
    }


def get_surface_path(surface_id):
    for surface in _surface_files(CASE_ROOT):
        if surface["id"] == surface_id:
            return surface["path"]
    return None


def launch_case_file():
    if not CASE_FILE.exists():
        return False, "File .foam tidak ditemukan."

    paraview_command = _find_paraview_command()
    if paraview_command:
        subprocess.Popen([paraview_command, str(CASE_FILE)], cwd=CASE_ROOT)
        return True, "Case .foam dikirim ke ParaView."

    if hasattr(os, "startfile"):
        try:
            os.startfile(str(CASE_FILE))
            return True, "Case .foam dibuka lewat aplikasi default Windows."
        except OSError as exc:
            return False, f"Gagal membuka .foam: {exc}"

    return False, "ParaView belum ditemukan di PATH."


def _time_directories(case_root):
    time_names = [
        item.name
        for item in case_root.iterdir()
        if item.is_dir() and _parse_time(item.name) is not None
    ]
    return sorted(time_names, key=lambda value: _parse_time(value))


def _field_names(time_path):
    if not time_path.exists():
        return []

    fields = [
        item.name
        for item in time_path.iterdir()
        if item.is_file() and not item.name.startswith(".")
    ]
    return sorted(fields, key=str.lower)


def _processor_directories(case_root):
    processors = [
        item.name
        for item in case_root.iterdir()
        if item.is_dir() and re.fullmatch(r"processor\d+", item.name)
    ]
    return sorted(processors, key=lambda name: int(name.removeprefix("processor")))


def _surface_files(case_root):
    surfaces_root = case_root / "postProcessing" / "surfaces"
    if not surfaces_root.exists():
        return []

    surfaces = []
    for time_dir in _time_directories(surfaces_root):
        surface_time_dir = surfaces_root / time_dir
        for surface_path in sorted(surface_time_dir.glob("*.vtp"), key=lambda path: path.name.lower()):
            header = _read_surface_header(surface_path)
            surface_id = f"{time_dir}{SURFACE_ID_SEPARATOR}{surface_path.name}"
            surfaces.append(
                {
                    "id": surface_id,
                    "path": surface_path,
                    "name": surface_path.name,
                    "label": surface_path.stem,
                    "time": time_dir,
                    "points": header["points"],
                    "polys": header["polys"],
                    "points_label": _format_count(header["points"]),
                    "polys_label": _format_count(header["polys"]),
                    "size": _format_bytes(surface_path.stat().st_size),
                    "size_bytes": surface_path.stat().st_size,
                }
            )

    return sorted(surfaces, key=lambda item: (item["size_bytes"], item["name"].lower()))


def _default_surface(surfaces):
    if not surfaces:
        return None
    return surfaces[0]


def _read_surface_header(surface_path):
    with surface_path.open("r", encoding="utf-8", errors="ignore") as handle:
        header = handle.read(4096)
    match = re.search(
        r"<Piece\s+[^>]*NumberOfPoints=['\"](?P<points>\d+)['\"][^>]*NumberOfPolys=['\"](?P<polys>\d+)['\"]",
        header,
    )
    if not match:
        return {"points": 0, "polys": 0}

    return {
        "points": int(match.group("points")),
        "polys": int(match.group("polys")),
    }


def _parse_time(value):
    try:
        return float(value)
    except ValueError:
        return None


def _find_paraview_command():
    for command in ("paraview", "paraview.exe"):
        resolved = shutil.which(command)
        if resolved:
            return resolved
    return None


def _format_count(value):
    return f"{value:,}"


def _format_bytes(size):
    if size < 1024:
        return f"{size} B"

    value = float(size)
    for unit in ("KB", "MB", "GB"):
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"

    return f"{value:.1f} TB"

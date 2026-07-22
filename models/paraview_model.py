import os
import re
import base64
import shutil
import struct
import subprocess
import tempfile
from array import array
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = APP_ROOT.parent
CASE_DIR_NAME = "sprayDryer-6.0.0-onProduct-Trial02"
CASE_FILE_NAME = "case.foam"
CASE_ROOT = WORKSPACE_ROOT / CASE_DIR_NAME
CASE_FILE = CASE_ROOT / CASE_FILE_NAME
CACHE_ROOT = CASE_ROOT / "postProcessing" / "webInternalMesh"
INTERNAL_MESH_CACHE = CACHE_ROOT / "internalMesh.vtp"

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
    internal_mesh = _internal_mesh_info(CASE_ROOT) if case_exists else None

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
        "internal_mesh": internal_mesh,
        "paraview_command": _find_paraview_command(),
    }


def get_surface_path(surface_id):
    for surface in _surface_files(CASE_ROOT):
        if surface["id"] == surface_id:
            return surface["path"]
    return None


def get_internal_mesh_path():
    mesh_info = _internal_mesh_info(CASE_ROOT)
    if not mesh_info or not mesh_info["available"]:
        return None

    source_paths = [
        CASE_ROOT / "constant" / "polyMesh" / name
        for name in ("points", "faces", "boundary")
    ]
    cache_is_current = INTERNAL_MESH_CACHE.exists() and all(
        INTERNAL_MESH_CACHE.stat().st_mtime >= path.stat().st_mtime
        for path in source_paths
    )
    if cache_is_current:
        return INTERNAL_MESH_CACHE

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    _write_internal_mesh_vtp(mesh_info, INTERNAL_MESH_CACHE)
    return INTERNAL_MESH_CACHE


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


def _internal_mesh_info(case_root):
    poly_mesh = case_root / "constant" / "polyMesh"
    points_path = poly_mesh / "points"
    faces_path = poly_mesh / "faces"
    boundary_path = poly_mesh / "boundary"
    required_paths = (points_path, faces_path, boundary_path)
    available = all(path.exists() for path in required_paths)

    info = {
        "id": "internalMesh",
        "label": "internalMesh",
        "name": "internalMesh",
        "available": available,
        "cache_path": str(INTERNAL_MESH_CACHE),
        "cache_exists": INTERNAL_MESH_CACHE.exists(),
        "size": _format_bytes(INTERNAL_MESH_CACHE.stat().st_size) if INTERNAL_MESH_CACHE.exists() else "-",
        "points": 0,
        "faces": 0,
        "points_label": "-",
        "faces_label": "-",
    }
    if not available:
        return info

    patches = _boundary_patches(boundary_path)
    if not patches:
        return info

    start_face = min(patch["start_face"] for patch in patches)
    end_face = max(patch["start_face"] + patch["n_faces"] for patch in patches)
    face_count = end_face - start_face
    info.update(
        {
            "start_face": start_face,
            "end_face": end_face,
            "faces": face_count,
            "faces_label": _format_count(face_count),
            "patches": patches,
        }
    )

    try:
        point_count, _ = _openfoam_binary_list_header(points_path)
        info["source_points"] = point_count
        info["points_label"] = _format_count(point_count)
    except ValueError:
        pass

    return info


def _boundary_patches(boundary_path):
    text = boundary_path.read_text(encoding="utf-8", errors="ignore")
    patch_pattern = re.compile(
        r"(?P<name>\w+)\s*\{(?P<body>.*?)\}",
        re.DOTALL,
    )
    patches = []
    for match in patch_pattern.finditer(text):
        body = match.group("body")
        n_faces = re.search(r"\bnFaces\s+(?P<value>\d+)\s*;", body)
        start_face = re.search(r"\bstartFace\s+(?P<value>\d+)\s*;", body)
        if not n_faces or not start_face:
            continue
        patches.append(
            {
                "name": match.group("name"),
                "n_faces": int(n_faces.group("value")),
                "start_face": int(start_face.group("value")),
            }
        )
    return patches


def _write_internal_mesh_vtp(mesh_info, cache_path):
    poly_mesh = CASE_ROOT / "constant" / "polyMesh"
    points_path = poly_mesh / "points"
    faces_path = poly_mesh / "faces"

    point_count, points_start = _openfoam_binary_list_header(points_path)
    face_count, offsets_start = _openfoam_binary_list_header(faces_path)
    labels_count, labels_start = _face_labels_header(faces_path, offsets_start, face_count)

    start_face = mesh_info["start_face"]
    end_face = mesh_info["end_face"]
    boundary_face_count = end_face - start_face
    if start_face < 0 or end_face > face_count:
        raise ValueError("range boundary internalMesh tidak valid")

    connectivity = array("I")
    offsets = array("I")
    point_map = {}
    point_ids = array("I")
    point_cursor = 0

    with faces_path.open("rb") as handle:
        handle.seek(offsets_start + (start_face * 4))
        offset_values = array("I")
        offset_read_count = boundary_face_count + (0 if end_face == face_count else 1)
        offset_values.fromfile(handle, offset_read_count)
        if _needs_byteswap():
            offset_values.byteswap()

        first_label_offset = offset_values[0]
        last_label_offset = labels_count if end_face == face_count else offset_values[-1]
        label_total = last_label_offset - first_label_offset
        if first_label_offset < 0 or last_label_offset > labels_count:
            raise ValueError("offset face internalMesh tidak valid")

        handle.seek(labels_start + (first_label_offset * 4))
        original_labels = array("I")
        original_labels.fromfile(handle, label_total)
        if _needs_byteswap():
            original_labels.byteswap()

    label_cursor = 0
    previous_offset = first_label_offset
    face_end_offsets = offset_values[1:] if end_face < face_count else list(offset_values[1:]) + [labels_count]
    for offset in face_end_offsets:
        vertex_count = offset - previous_offset
        for _ in range(vertex_count):
            original_point = original_labels[label_cursor]
            mapped_point = point_map.get(original_point)
            if mapped_point is None:
                if original_point >= point_count:
                    raise ValueError("point face internalMesh melebihi jumlah points")
                mapped_point = point_cursor
                point_map[original_point] = mapped_point
                point_ids.append(original_point)
                point_cursor += 1
            connectivity.append(mapped_point)
            label_cursor += 1
        offsets.append(len(connectivity))
        previous_offset = offset

    positions = _read_compacted_positions(points_path, points_start, point_ids)
    tmp_handle = tempfile.NamedTemporaryFile("wb", delete=False, dir=cache_path.parent, suffix=".vtp")
    tmp_path = Path(tmp_handle.name)
    try:
        with tmp_handle:
            _write_vtp_xml(tmp_handle, positions, connectivity, offsets)
        tmp_path.replace(cache_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _openfoam_binary_list_header(path):
    with path.open("rb") as handle:
        header = handle.read(4096)
    matches = list(re.finditer(rb"\n(\d+)\n\(", header))
    if not matches:
        raise ValueError(f"header OpenFOAM binary tidak ditemukan: {path.name}")
    match = matches[-1]
    return int(match.group(1)), match.end()


def _face_labels_header(path, offsets_start, face_count):
    offsets_end = offsets_start + (face_count * 4)
    with path.open("rb") as handle:
        handle.seek(offsets_end)
        header = handle.read(128)
    match = re.search(rb"\)\n(\d+)\n\(", header)
    if not match:
        raise ValueError("header label faces OpenFOAM tidak ditemukan")
    return int(match.group(1)), offsets_end + match.end()


def _read_compacted_positions(points_path, points_start, point_ids):
    positions = array("f", [0.0]) * (len(point_ids) * 3)
    with points_path.open("rb") as handle:
        for compact_index, original_point in enumerate(point_ids):
            handle.seek(points_start + (original_point * 24))
            x, y, z = struct.unpack("<ddd", handle.read(24))
            base = compact_index * 3
            positions[base] = x
            positions[base + 1] = y
            positions[base + 2] = z
    if _needs_byteswap():
        positions.byteswap()
    return positions


def _write_vtp_xml(handle, positions, connectivity, offsets):
    point_count = len(positions) // 3
    poly_count = len(offsets)
    handle.write(
        (
            '<?xml version="1.0"?>\n'
            '<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian" header_type="UInt32">\n'
            "  <PolyData>\n"
            f'    <Piece NumberOfPoints="{point_count}" NumberOfVerts="0" NumberOfLines="0" '
            f'NumberOfStrips="0" NumberOfPolys="{poly_count}">\n'
            '      <Points>\n'
            '        <DataArray type="Float32" NumberOfComponents="3" format="binary">\n'
        ).encode("ascii")
    )
    _write_base64_array(handle, positions)
    handle.write(
        (
            "\n"
            "        </DataArray>\n"
            "      </Points>\n"
            "      <Polys>\n"
            '        <DataArray type="Int32" Name="connectivity" format="binary">\n'
        ).encode("ascii")
    )
    _write_base64_array(handle, connectivity)
    handle.write(
        (
            "\n"
            "        </DataArray>\n"
            '        <DataArray type="Int32" Name="offsets" format="binary">\n'
        ).encode("ascii")
    )
    _write_base64_array(handle, offsets)
    handle.write(
        (
            "\n"
            "        </DataArray>\n"
            "      </Polys>\n"
            "    </Piece>\n"
            "  </PolyData>\n"
            "</VTKFile>\n"
        ).encode("ascii")
    )


def _write_base64_array(handle, values):
    payload = memoryview(values).cast("B")
    handle.write(base64.b64encode(struct.pack("<I", payload.nbytes) + payload.tobytes()))


def _needs_byteswap():
    return struct.pack("=I", 1) != struct.pack("<I", 1)


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

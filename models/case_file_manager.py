import json
import math
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath


class CaseFileError(ValueError):
    """Error yang aman untuk ditampilkan kepada pengguna file manager."""


class CaseFileManager:
    MAX_EDIT_BYTES = 2 * 1024 * 1024
    MAX_UPLOAD_FILES = 100
    PAGE_SIZE = 100
    BINARY_SUFFIXES = {
        ".7z",
        ".avi",
        ".bin",
        ".bmp",
        ".doc",
        ".docx",
        ".exe",
        ".foam.gz",
        ".gif",
        ".gz",
        ".ico",
        ".jpeg",
        ".jpg",
        ".mp4",
        ".pdf",
        ".png",
        ".rar",
        ".so",
        ".stl",
        ".tar",
        ".tif",
        ".tiff",
        ".webp",
        ".xls",
        ".xlsx",
        ".zip",
    }
    RESULT_FOLDER_NAMES = {"postprocessing", "vtk"}

    def __init__(self, case_root, state_root, report_root=None, graph_root=None):
        self.case_root = Path(case_root).resolve()
        self.state_root = Path(state_root).resolve()
        self.report_root = Path(report_root).resolve() if report_root else None
        self.graph_root = Path(graph_root).resolve() if graph_root else None
        self.manifest_path = self.state_root / "uploads.json"
        self.backup_root = self.state_root / "backups"

    @staticmethod
    def _format_size(size):
        units = ("B", "KB", "MB", "GB", "TB")
        value = float(size)
        unit = units[0]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                break
            value /= 1024
        if unit == "B":
            return f"{int(value)} {unit}"
        return f"{value:.1f} {unit}"

    @staticmethod
    def _is_log_name(filename):
        lowered = filename.casefold()
        suffix = Path(lowered).suffix
        return (
            lowered == "log"
            or lowered.startswith(("log.", "log_", "log-"))
            or suffix in {".log", ".out", ".err"}
        )

    @staticmethod
    def _is_numeric_result_folder(name):
        try:
            value = Decimal(name)
            return value.is_finite() and value > 0
        except InvalidOperation:
            return False

    @classmethod
    def _is_result_path(cls, relative_path):
        parts = PurePosixPath(relative_path).parts
        if not parts:
            return False

        first = parts[0].casefold()
        if first in cls.RESULT_FOLDER_NAMES or re.fullmatch(r"processor\d+", first):
            return True
        if cls._is_numeric_result_folder(parts[0]):
            return True
        return len(parts) >= 2 and first == "constant" and parts[1].casefold() == "polymesh"

    @staticmethod
    def _safe_archive_name(value):
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "openfoam-case"

    def _iter_files(self, root=None):
        scan_root = Path(root or self.case_root)
        if not scan_root.exists():
            return

        for current, directory_names, file_names in os.walk(scan_root, followlinks=False):
            current_path = Path(current)
            directory_names[:] = [
                name
                for name in directory_names
                if not (current_path / name).is_symlink()
            ]
            for filename in file_names:
                path = current_path / filename
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                except OSError:
                    continue
                yield path

    def _normalize_relative(self, relative_path, allow_root=False):
        raw_value = str(relative_path or "").replace("\\", "/").strip()
        if not raw_value:
            if allow_root:
                return PurePosixPath()
            raise CaseFileError("Path file wajib diisi.")

        pure_path = PurePosixPath(raw_value)
        parts = tuple(part for part in pure_path.parts if part not in {"", "."})
        if pure_path.is_absolute() or any(part == ".." or ":" in part or "\x00" in part for part in parts):
            raise CaseFileError("Path file tidak aman atau berada di luar folder case.")
        if not parts and not allow_root:
            raise CaseFileError("Path file wajib diisi.")
        return PurePosixPath(*parts)

    def resolve_path(self, relative_path, must_exist=True, allow_root=False):
        relative = self._normalize_relative(relative_path, allow_root=allow_root)
        unresolved = self.case_root.joinpath(*relative.parts)
        current = self.case_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise CaseFileError("Symlink tidak dapat diakses melalui Case File Manager.")

        candidate = unresolved.resolve(strict=False)
        try:
            candidate.relative_to(self.case_root)
        except ValueError as exc:
            raise CaseFileError("Path file tidak aman atau berada di luar folder case.") from exc

        if must_exist and not candidate.exists():
            raise CaseFileError("File tidak ditemukan di dalam case.")
        return candidate

    def _is_editable_path(self, path):
        try:
            stat = path.stat()
            if stat.st_size > self.MAX_EDIT_BYTES:
                return False
            if path.suffix.casefold() in self.BINARY_SUFFIXES:
                return False
            with path.open("rb") as handle:
                sample = handle.read(8192)
            if b"\x00" in sample:
                return False
            sample.decode("utf-8-sig")
            return True
        except (OSError, UnicodeDecodeError):
            return False

    def _record_for(self, path):
        relative = path.relative_to(self.case_root).as_posix()
        stat = path.stat()
        is_log = self._is_log_name(path.name)
        editable = self._is_editable_path(path)
        if is_log:
            kind = "log"
            label = "Log"
            icon = "bi-file-earmark-text"
        elif path.suffix.casefold() == ".stl":
            kind = "stl"
            label = "STL"
            icon = "bi-badge-3d"
        elif editable:
            kind = "text"
            label = "Text"
            icon = "bi-file-earmark-code"
        else:
            kind = "binary"
            label = "Binary"
            icon = "bi-file-earmark-binary"

        return {
            "name": path.name,
            "path": relative,
            "folder": PurePosixPath(relative).parent.as_posix(),
            "size": stat.st_size,
            "size_label": self._format_size(stat.st_size),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%d %b %Y, %H:%M"),
            "kind": kind,
            "kind_label": label,
            "icon": icon,
            "editable": editable,
            "is_result": self._is_result_path(relative),
        }

    def list_files(self, search="", category="all", page=1):
        records = []
        directories = {"."}
        total_bytes = 0
        editable_count = 0
        counts = {"all": 0, "text": 0, "stl": 0, "log": 0, "binary": 0, "result": 0}

        if self.case_root.exists():
            for path in self._iter_files():
                try:
                    record = self._record_for(path)
                except OSError:
                    continue
                records.append(record)
                total_bytes += record["size"]
                editable_count += int(record["editable"])
                counts["all"] += 1
                counts[record["kind"]] += 1
                if record["is_result"]:
                    counts["result"] += 1

                parent = PurePosixPath(record["path"]).parent
                while parent.as_posix() != ".":
                    directories.add(parent.as_posix())
                    parent = parent.parent

        normalized_search = search.strip().casefold()
        valid_categories = set(counts)
        selected_category = category if category in valid_categories else "all"
        filtered = [
            record
            for record in records
            if (not normalized_search or normalized_search in record["path"].casefold())
            and (
                selected_category == "all"
                or (selected_category == "result" and record["is_result"])
                or record["kind"] == selected_category
            )
        ]
        filtered.sort(key=lambda record: record["path"].casefold())

        total_filtered = len(filtered)
        total_pages = max(1, math.ceil(total_filtered / self.PAGE_SIZE))
        try:
            current_page = max(1, min(int(page), total_pages))
        except (TypeError, ValueError):
            current_page = 1
        start = (current_page - 1) * self.PAGE_SIZE

        return {
            "files": filtered[start : start + self.PAGE_SIZE],
            "stats": {
                **counts,
                "editable": editable_count,
                "total_bytes": total_bytes,
                "total_size_label": self._format_size(total_bytes),
            },
            "directories": sorted(directories, key=lambda value: (value != ".", value.casefold())),
            "search": search.strip(),
            "category": selected_category,
            "page": current_page,
            "pages": total_pages,
            "total_filtered": total_filtered,
            "page_size": self.PAGE_SIZE,
        }

    def read_text(self, relative_path):
        path = self.resolve_path(relative_path)
        if not path.is_file() or not self._is_editable_path(path):
            raise CaseFileError("File ini berupa binary, terlalu besar, atau bukan UTF-8 sehingga tidak dapat diedit.")
        try:
            content = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            raise CaseFileError(f"File gagal dibaca: {exc}") from exc
        return {"path": path.relative_to(self.case_root).as_posix(), "content": content}

    def save_text(self, relative_path, content):
        path = self.resolve_path(relative_path)
        if not path.is_file() or not self._is_editable_path(path):
            raise CaseFileError("File ini tidak dapat diedit sebagai teks UTF-8.")

        encoded = str(content).encode("utf-8")
        if len(encoded) > self.MAX_EDIT_BYTES:
            raise CaseFileError("Isi file melebihi batas editor 2 MB.")

        descriptor = None
        temporary_name = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(prefix=".case-edit-", dir=path.parent)
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = None
                handle.write(encoded)
            shutil.copymode(path, temporary_name)
            os.replace(temporary_name, path)
            temporary_name = None
        except OSError as exc:
            raise CaseFileError(f"Perubahan file gagal disimpan: {exc}") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)

    def _load_manifest(self):
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            entries = raw.get("entries", {})
            return entries if isinstance(entries, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save_manifest(self, entries):
        self.state_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix="uploads-", suffix=".json", dir=self.state_root)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"entries": entries}, handle, indent=2, sort_keys=True)
            os.replace(temporary_name, self.manifest_path)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    def _backup_path(self, backup_name):
        if not re.fullmatch(r"[0-9a-f]{32}", str(backup_name or "")):
            return None
        return self.backup_root / backup_name

    def upload_files(self, file_storages, target_folder="", replace=False):
        uploads = [storage for storage in file_storages if (getattr(storage, "filename", "") or "").strip()]
        if not uploads:
            raise CaseFileError("Pilih minimal satu file untuk diupload.")
        if len(uploads) > self.MAX_UPLOAD_FILES:
            raise CaseFileError(f"Maksimal {self.MAX_UPLOAD_FILES} file dalam satu upload.")

        target_relative = self._normalize_relative(target_folder, allow_root=True)
        target_dir = self.resolve_path(target_relative.as_posix(), must_exist=False, allow_root=True)
        if target_dir.exists() and not target_dir.is_dir():
            raise CaseFileError("Lokasi tujuan bukan sebuah folder.")

        destinations = []
        seen = set()
        for storage in uploads:
            filename = (storage.filename or "").strip()
            if (
                filename in {".", ".."}
                or Path(filename).name != filename
                or any(character in filename for character in ("/", "\\", ":", "\x00"))
            ):
                raise CaseFileError(f"Nama file tidak aman: {filename}")
            destination = (target_dir / filename).resolve(strict=False)
            try:
                destination.relative_to(self.case_root)
            except ValueError as exc:
                raise CaseFileError(f"Lokasi file tidak aman: {filename}") from exc
            relative = destination.relative_to(self.case_root).as_posix()
            if relative.casefold() in seen:
                raise CaseFileError(f"File duplikat dipilih: {filename}")
            seen.add(relative.casefold())
            if destination.exists() and (destination.is_dir() or destination.is_symlink()):
                raise CaseFileError(f"Target bukan file biasa: {relative}")
            if destination.exists() and not replace:
                raise CaseFileError(f"File sudah ada: {relative}. Aktifkan opsi replace untuk menggantinya.")
            destinations.append((storage, destination, relative))

        self.state_root.mkdir(parents=True, exist_ok=True)
        staging_root = Path(tempfile.mkdtemp(prefix="upload-", dir=self.state_root))
        staged = []
        try:
            for index, (storage, destination, relative) in enumerate(destinations):
                staged_path = staging_root / str(index)
                storage.save(staged_path)
                staged.append((staged_path, destination, relative))

            entries = self._load_manifest()
            added = 0
            replaced = 0
            for staged_path, destination, relative in staged:
                destination.parent.mkdir(parents=True, exist_ok=True)
                entry = entries.get(relative)
                if destination.exists():
                    replaced += 1
                    if not entry:
                        self.backup_root.mkdir(parents=True, exist_ok=True)
                        backup_name = uuid.uuid4().hex
                        backup_path = self.backup_root / backup_name
                        shutil.copy2(destination, backup_path)
                        entry = {"kind": "replaced", "backup": backup_name}
                else:
                    added += 1
                    entry = entry or {"kind": "created"}
                os.replace(staged_path, destination)
                entries[relative] = entry
            self._save_manifest(entries)
        except OSError as exc:
            raise CaseFileError(f"Upload gagal disimpan: {exc}") from exc
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)

        return {"added": added, "replaced": replaced, "files": [item[2] for item in destinations]}

    def delete_file(self, relative_path):
        path = self.resolve_path(relative_path)
        if not path.is_file() or path.is_symlink():
            raise CaseFileError("Target bukan file biasa dan tidak dapat dihapus.")

        relative = path.relative_to(self.case_root).as_posix()
        try:
            path.unlink()
        except OSError as exc:
            raise CaseFileError(f"File gagal dihapus: {exc}") from exc

        entries = self._load_manifest()
        entry = entries.pop(relative, None)
        if entry:
            backup_path = self._backup_path(entry.get("backup"))
            if backup_path:
                backup_path.unlink(missing_ok=True)
            self._save_manifest(entries)
        return relative

    def _write_archive_entry(self, archive, path, archive_name):
        try:
            compression = zipfile.ZIP_STORED if path.suffix.casefold() in self.BINARY_SUFFIXES else zipfile.ZIP_DEFLATED
            archive.write(path, archive_name, compress_type=compression)
            return True
        except (FileNotFoundError, PermissionError, OSError):
            return False

    def _new_archive_path(self, prefix):
        descriptor, filename = tempfile.mkstemp(prefix=prefix, suffix=".zip")
        os.close(descriptor)
        return Path(filename)

    def build_case_archive(self):
        archive_path = self._new_archive_path("cfd-case-")
        case_prefix = self._safe_archive_name(self.case_root.name)
        file_count = 0
        try:
            with zipfile.ZipFile(archive_path, "w", allowZip64=True, compresslevel=1) as archive:
                for path in self._iter_files():
                    relative = path.relative_to(self.case_root).as_posix()
                    file_count += int(self._write_archive_entry(archive, path, f"{case_prefix}/{relative}"))

                extras = ((self.report_root, "reports"), (self.graph_root, "graphs"))
                for extra_root, prefix in extras:
                    if not extra_root or not extra_root.exists():
                        continue
                    for path in self._iter_files(extra_root):
                        relative = path.relative_to(extra_root).as_posix()
                        file_count += int(self._write_archive_entry(archive, path, f"{prefix}/{relative}"))
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise

        if file_count == 0:
            archive_path.unlink(missing_ok=True)
            raise CaseFileError("Tidak ada file yang dapat dimasukkan ke ZIP case.")
        return archive_path, file_count

    def _log_sources(self):
        for path in self._iter_files():
            if self._is_log_name(path.name):
                yield path, f"case_logs/{path.relative_to(self.case_root).as_posix()}"
        if self.graph_root and self.graph_root.parent.exists():
            graph_base = self.graph_root.parent
            for path in self._iter_files(graph_base):
                if self._is_log_name(path.name):
                    yield path, f"graph_logs/{path.relative_to(graph_base).as_posix()}"

    def build_logs_archive(self):
        archive_path = self._new_archive_path("cfd-logs-")
        file_count = 0
        try:
            with zipfile.ZipFile(archive_path, "w", allowZip64=True, compresslevel=1) as archive:
                for path, archive_name in self._log_sources():
                    file_count += int(self._write_archive_entry(archive, path, archive_name))
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise

        if file_count == 0:
            archive_path.unlink(missing_ok=True)
            raise CaseFileError("Tidak ada file log yang ditemukan.")
        return archive_path, file_count

    def _count_files_in(self, path):
        if not path.exists() or path.is_symlink():
            return 0
        if path.is_file():
            return 1
        return sum(1 for _ in self._iter_files(path))

    def _remove_empty_parents(self, path):
        current = path.parent
        while current != self.case_root:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def _clear_uploaded(self):
        entries = self._load_manifest()
        removed = 0
        restored = 0
        for relative, entry in list(entries.items()):
            try:
                path = self.resolve_path(relative, must_exist=False)
            except CaseFileError:
                continue

            if entry.get("kind") == "replaced":
                backup_path = self._backup_path(entry.get("backup"))
                if backup_path and backup_path.is_file() and not backup_path.is_symlink():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_path, path)
                    restored += 1
                    backup_path.unlink(missing_ok=True)
            elif path.is_file() and not path.is_symlink():
                path.unlink()
                self._remove_empty_parents(path)
                removed += 1

        self._save_manifest({})
        return {"files": removed, "directories": 0, "restored": restored}

    def _clear_logs(self):
        files = [path for path in self._iter_files() if self._is_log_name(path.name)]
        removed = 0
        for path in files:
            try:
                path.unlink()
                removed += 1
            except FileNotFoundError:
                continue
        return {"files": removed, "directories": 0, "restored": 0}

    def _clear_results(self):
        targets = []
        if self.case_root.exists():
            for child in self.case_root.iterdir():
                if child.is_symlink() or not child.is_dir():
                    continue
                lowered = child.name.casefold()
                if (
                    lowered in self.RESULT_FOLDER_NAMES
                    or re.fullmatch(r"processor\d+", lowered)
                    or self._is_numeric_result_folder(child.name)
                ):
                    targets.append(child)
            poly_mesh = self.case_root / "constant" / "polyMesh"
            if poly_mesh.is_dir() and not poly_mesh.is_symlink():
                targets.append(poly_mesh)

        removed_files = 0
        removed_directories = 0
        for target in targets:
            removed_files += self._count_files_in(target)
            shutil.rmtree(target)
            removed_directories += 1

        log_result = self._clear_logs()
        return {
            "files": removed_files + log_result["files"],
            "directories": removed_directories,
            "restored": 0,
        }

    def clear(self, mode):
        if mode == "logs":
            return self._clear_logs()
        if mode == "results":
            return self._clear_results()
        if mode == "uploads":
            return self._clear_uploaded()
        if mode == "reset":
            upload_result = self._clear_uploaded()
            result = self._clear_results()
            result["files"] += upload_result["files"]
            result["restored"] += upload_result["restored"]
            return result
        raise CaseFileError("Pilihan clear/reset tidak dikenal.")

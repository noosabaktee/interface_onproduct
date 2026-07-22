import json
import os
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import threading
import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - only used by local Windows development
    fcntl = None

from models.paraview_model import CASE_FILE, CASE_ROOT


DEFAULT_PORT = 11112
MAX_LOG_LINES = 300
MAX_LOG_FILE_BYTES = 8 * 1024 * 1024
MAX_LOG_TAIL_BYTES = 512 * 1024
_fallback_lock = threading.Lock()


def _runtime_root():
    return Path(
        os.environ.get(
            "PVSERVER_RUNTIME_DIR",
            "/run/kmi-cfd-paraview",
        )
    )


def _state_path():
    return _runtime_root() / "state.json"


def _log_path():
    return _runtime_root() / "pvserver.log"


def _lock_path():
    return _runtime_root() / "manager.lock"


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _configured_port(name, default):
    raw_value = os.environ.get(name, str(default))
    try:
        port = int(raw_value)
    except (TypeError, ValueError):
        return default
    return port if 1 <= port <= 65535 else default


def get_server_port():
    return _configured_port("PVSERVER_PORT", DEFAULT_PORT)


def get_public_port():
    return _configured_port("PVSERVER_PUBLIC_PORT", get_server_port())


def _clean_host(value):
    host = (value or "").strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0].strip()

    if host.startswith("[") and "]" in host:
        return host[1 : host.index("]")]
    if host.count(":") == 1:
        name, possible_port = host.rsplit(":", 1)
        if possible_port.isdigit():
            host = name

    return "".join(character for character in host if character.isalnum() or character in ".-:")


def _url_host(host):
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def get_connection_config(fallback_host=None):
    configured_host = _clean_host(os.environ.get("PVSERVER_PUBLIC_HOST"))
    detected_host = _clean_host(fallback_host)
    public_host = configured_host or detected_host or "alamat-vps-anda"
    public_port = get_public_port()
    configured_ssh_user = os.environ.get("PVSERVER_SSH_USER", "").strip()
    ssh_user = configured_ssh_user or "user-vps"

    return {
        "public_host": public_host,
        "public_port": public_port,
        "server_port": get_server_port(),
        "connection_host": public_host,
        "tunnel_host": "localhost",
        "public_host_configured": bool(configured_host),
        "ssh_user_configured": bool(configured_ssh_user),
        "connection_url": f"cs://{_url_host(public_host)}:{public_port}",
        "ssh_command": (
            f"ssh -L {public_port}:localhost:{public_port} "
            f"{ssh_user}@{public_host} -p 8822"
        ),
        "tunnel_connection_url": f"cs://localhost:{public_port}",
    }


def _default_state():
    return {
        "status": "idle",
        "running": False,
        "pid": None,
        "last_pid": None,
        "port": get_server_port(),
        "case_path": str(CASE_FILE),
        "case_name": CASE_FILE.name,
        "binary": None,
        "server_version": None,
        "render_backend": None,
        "render_warning": None,
        "started_at": None,
        "stopped_at": None,
        "stop_requested": False,
        "stop_failed": False,
        "ready_at": None,
        "connected_at": None,
        "exit_observed_at": None,
        "message": "Remote ParaView belum dijalankan.",
    }


def _ensure_runtime_root():
    runtime_root = _runtime_root()
    try:
        runtime_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        runtime_stat = runtime_root.stat(follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError(f"Runtime directory pvserver tidak aman: {exc}") from exc

    if runtime_root.is_symlink() or not stat.S_ISDIR(runtime_stat.st_mode):
        raise RuntimeError("Runtime path pvserver harus berupa directory, bukan symlink.")
    if runtime_stat.st_uid != os.geteuid():
        raise RuntimeError("Runtime directory pvserver dimiliki user lain.")

    if stat.S_IMODE(runtime_stat.st_mode) != 0o700:
        os.chmod(runtime_root, 0o700)
    return runtime_root


@contextmanager
def _manager_lock():
    _ensure_runtime_root()

    with _fallback_lock:
        with _lock_path().open("a+", encoding="utf-8") as lock_handle:
            try:
                os.chmod(_lock_path(), 0o600)
            except OSError:
                pass

            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _load_state():
    try:
        stored = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return _default_state()

    state = _default_state()
    if isinstance(stored, dict):
        state.update(stored)
    return state


def _save_state(state):
    runtime_root = _ensure_runtime_root()
    temporary_path = runtime_root / f".state-{os.getpid()}-{threading.get_ident()}.tmp"
    temporary_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.chmod(temporary_path, 0o600)
    temporary_path.replace(_state_path())


def _append_log(message):
    _ensure_runtime_root()
    with _log_path().open("a", encoding="utf-8") as log_handle:
        log_handle.write(f"{message.rstrip()}\n")


def _read_log_tail(max_bytes=MAX_LOG_TAIL_BYTES):
    try:
        with _log_path().open("rb") as log_handle:
            log_handle.seek(0, os.SEEK_END)
            size = log_handle.tell()
            start = max(0, size - max_bytes)
            log_handle.seek(start)
            data = log_handle.read()
    except OSError:
        return []

    if start and b"\n" in data:
        data = data.split(b"\n", 1)[1]
    elif start:
        data = b""

    text = data.decode("utf-8", errors="replace")
    return list(deque(text.splitlines(), maxlen=MAX_LOG_LINES))


def _cap_log_if_needed():
    try:
        if _log_path().stat().st_size <= MAX_LOG_FILE_BYTES:
            return
    except OSError:
        return

    retained_lines = _read_log_tail()
    retained = (
        "[SYSTEM] Output lama dipangkas agar log tetap terbatas.\n"
        + "\n".join(retained_lines)
        + ("\n" if retained_lines else "")
    ).encode("utf-8", errors="replace")

    try:
        descriptor = os.open(_log_path(), os.O_WRONLY | os.O_TRUNC | os.O_APPEND)
        try:
            os.write(descriptor, retained)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def _tail_log():
    _cap_log_if_needed()
    return _read_log_tail()


def _find_pvserver():
    configured_binary = os.environ.get("PVSERVER_BINARY", "").strip()
    candidates = []
    if configured_binary:
        candidates.append(Path(configured_binary))

    resolved = shutil.which("pvserver")
    if resolved:
        candidates.append(Path(resolved))

    candidates.extend(
        [
            Path("/usr/local/bin/pvserver"),
            Path("/opt/paraview-5.10.1/bin/pvserver"),
        ]
    )
    candidates.extend(
        sorted(
            Path("/opt").glob("paraview*/bin/pvserver"),
            reverse=True,
        )
    )

    for candidate in candidates:
        try:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate.resolve())
        except OSError:
            continue
    return None


def _server_version(binary):
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    version_line = (result.stdout or result.stderr or "").strip().splitlines()
    if not version_line:
        return None
    return version_line[-1].replace("paraview version", "").strip() or None


def _build_server_command(binary, port):
    configured_backend = os.environ.get("PVSERVER_HEADLESS_BACKEND", "auto").strip().lower()
    display = os.environ.get("DISPLAY", "").strip()
    xvfb_run = shutil.which("xvfb-run")
    pvserver_options = [
        "--no-mpi",
        "--force-offscreen-rendering",
        f"--server-port={port}",
    ]

    if configured_backend in {"osmesa", "egl"}:
        return [binary, *pvserver_options], configured_backend.upper(), None

    if display:
        return [binary, *pvserver_options], f"X11 ({display})", None

    if xvfb_run:
        paraview_root = Path(binary).resolve().parent.parent
        bundled_mesa = paraview_root / "lib" / "mesa" / "libGL.so.1"
        launcher_options = (
            ["--mesa", "--backend", "llvmpipe"]
            if bundled_mesa.is_file()
            else []
        )
        backend_name = (
            "Xvfb + bundled Mesa llvmpipe"
            if launcher_options
            else "Xvfb + Mesa software"
        )
        return (
            [
                xvfb_run,
                "-a",
                "-s",
                "-screen 0 1920x1080x24 -noreset +extension GLX +render",
                binary,
                *launcher_options,
                *pvserver_options,
            ],
            backend_name,
            None,
        )

    return (
        [binary, *pvserver_options],
        "Offscreen (belum terverifikasi)",
        (
            "Xvfb/display tidak ditemukan. Server dapat menerima koneksi, "
            "tetapi remote rendering mungkin gagal."
        ),
    )


def _pid_exists(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False

    try:
        stat_parts = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    except OSError:
        return False
    return len(stat_parts) >= 3 and stat_parts[2] != "Z"


def _within_startup_grace(state, seconds=15):
    if state.get("status") != "starting" or not state.get("started_at"):
        return False

    try:
        started_at = datetime.fromisoformat(state["started_at"])
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - started_at).total_seconds()
    except (TypeError, ValueError):
        return False
    return 0 <= age <= seconds


def _seconds_since(value):
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - timestamp).total_seconds())
    except (TypeError, ValueError):
        return None


def _pid_matches_server(pid, port):
    if not _pid_exists(pid):
        return False

    try:
        command_line = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
            "utf-8",
            errors="replace",
        )
    except OSError:
        return False

    return "pvserver" in command_line and f"--server-port={port}" in command_line


def _state_process_alive(state):
    pid = state.get("pid")
    port = int(state.get("port") or get_server_port())
    return _pid_matches_server(pid, port) or (
        _pid_exists(pid) and _within_startup_grace(state)
    )


def _tcp_states_for_port(port):
    states = set()
    target_port = f"{port:04X}"

    for table_path in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            rows = table_path.read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue

        for row in rows:
            columns = row.split()
            if len(columns) < 4:
                continue
            local_address = columns[1]
            if ":" not in local_address:
                continue
            if local_address.rsplit(":", 1)[1].upper() == target_port:
                states.add(columns[3].upper())

    return states


def _port_available(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("0.0.0.0", port))
    except OSError:
        return False
    finally:
        sock.close()
    return True


def _log_failure_reason(lines):
    joined = "\n".join(lines).lower()
    failure_patterns = (
        ("address already in use", "Port pvserver sudah digunakan proses lain."),
        ("failed to bind", "pvserver gagal bind ke port yang dipilih."),
        ("bad x server connection", "Backend display untuk remote rendering terputus."),
        ("version mismatch", "Versi ParaView Desktop dan pvserver tidak kompatibel."),
        ("fatl|", "pvserver berhenti karena fatal signal."),
        ("error: exception occurred", "pvserver berhenti karena exception."),
    )
    for pattern, message in failure_patterns:
        if pattern in joined:
            return message
    return None


def _finalize_exited_state(state, return_code=None):
    lines = _tail_log()
    failure_reason = _log_failure_reason(lines)
    intentional_stop = state.get("stop_requested") or state.get("status") == "stopping"
    was_ready = bool(state.get("ready_at")) or any(
        "Accepting connection(s)" in line for line in lines
    )
    normal_exit = any("Exiting..." in line for line in lines)
    pid = state.get("pid")

    state["last_pid"] = pid or state.get("last_pid")
    state["pid"] = None
    state["running"] = False
    state["stop_requested"] = False
    state["stop_failed"] = False
    state["exit_observed_at"] = None
    state["stopped_at"] = _utc_now()

    if intentional_stop:
        state["status"] = "stopped"
        state["message"] = "Remote ParaView telah dihentikan."
        state.pop("error", None)
        _append_log("[SYSTEM] pvserver dihentikan oleh pengguna.")
    elif failure_reason:
        state["status"] = "failed"
        state["message"] = failure_reason
        state["error"] = failure_reason
        _append_log(f"[ERROR] {failure_reason}")
    elif return_code == 0 and was_ready:
        state["status"] = "stopped"
        state["message"] = "Sesi ParaView Desktop selesai dan server telah berhenti."
        state.pop("error", None)
        _append_log("[SYSTEM] Sesi remote selesai secara normal.")
    elif return_code is None and normal_exit and was_ready:
        state["status"] = "stopped"
        state["message"] = "Sesi ParaView Desktop selesai dan server telah berhenti."
        state.pop("error", None)
        _append_log("[SYSTEM] Sesi remote selesai secara normal.")
    else:
        exit_label = f"exit code {return_code}" if return_code is not None else "hasil yang tidak diketahui"
        state["status"] = "failed"
        state["message"] = f"pvserver berhenti dengan {exit_label}."
        state["error"] = state["message"]
        _append_log(f"[ERROR] {state['message']}")
    return state


def _refresh_state(state):
    pid = state.get("pid")
    port = int(state.get("port") or get_server_port())
    process_alive = _state_process_alive(state)

    if process_alive:
        tcp_states = _tcp_states_for_port(port)
        state["running"] = True
        state["exit_observed_at"] = None

        if state.get("stop_failed"):
            state["status"] = "failed"
            state["message"] = state.get("error") or "pvserver masih hidup setelah permintaan stop."
        elif state.get("stop_requested") or state.get("status") == "stopping":
            state["status"] = "stopping"
            state["message"] = "Menghentikan pvserver..."
        elif "01" in tcp_states:
            state["ready_at"] = state.get("ready_at") or _utc_now()
            state["connected_at"] = state.get("connected_at") or _utc_now()
            state["status"] = "connected"
            state["message"] = "ParaView Desktop sudah terhubung."
        elif "0A" in tcp_states:
            state["ready_at"] = state.get("ready_at") or _utc_now()
            state["status"] = "waiting"
            state["message"] = "Server aktif dan menunggu koneksi ParaView Desktop."
        else:
            state["status"] = "starting"
            state["message"] = "pvserver sedang disiapkan."
        return state

    if pid:
        if state.get("stop_requested") or state.get("status") in {"stopping", "stopped"}:
            return _finalize_exited_state(state)

        if not state.get("exit_observed_at"):
            state["exit_observed_at"] = _utc_now()
            state["running"] = False
            state["status"] = "finalizing"
            state["message"] = "Memeriksa hasil akhir proses pvserver..."
            return state

        exit_age = _seconds_since(state.get("exit_observed_at"))
        if exit_age is None or exit_age < 1.5:
            state["running"] = False
            state["status"] = "finalizing"
            state["message"] = "Memeriksa hasil akhir proses pvserver..."
            return state

        return _finalize_exited_state(state)
    else:
        state["running"] = False

    return state


def _state_response(state):
    response = dict(state)
    response["lines"] = _tail_log()
    response["public_port"] = get_public_port()
    return response


def get_server_state():
    with _manager_lock():
        state = _refresh_state(_load_state())
        _save_state(state)
        return _state_response(state)


def _watch_process(process):
    return_code = process.wait()

    with _manager_lock():
        state = _load_state()
        if state.get("pid") != process.pid:
            return
        state = _finalize_exited_state(state, return_code=return_code)
        _save_state(state)


def start_server():
    with _manager_lock():
        state = _refresh_state(_load_state())
        if state.get("running") or state.get("status") == "finalizing":
            return _state_response(state)

        port = get_server_port()
        binary = _find_pvserver()
        state.update(
            {
                "port": port,
                "case_path": str(CASE_FILE),
                "case_name": CASE_FILE.name,
                "binary": binary,
                "server_version": None,
                "render_backend": None,
                "render_warning": None,
                "pid": None,
                "running": False,
                "stop_requested": False,
                "stop_failed": False,
                "ready_at": None,
                "connected_at": None,
                "exit_observed_at": None,
                "started_at": None,
                "stopped_at": None,
            }
        )

        if not CASE_ROOT.is_dir():
            state["status"] = "failed"
            state["message"] = "Folder case OpenFOAM tidak ditemukan."
            state["error"] = state["message"]
            _save_state(state)
            return _state_response(state)

        try:
            CASE_FILE.touch(exist_ok=True)
        except OSError as exc:
            state["status"] = "failed"
            state["message"] = f"File {CASE_FILE.name} tidak dapat disiapkan."
            state["error"] = f"{state['message']} {exc}"
            _save_state(state)
            return _state_response(state)

        if not binary:
            state["status"] = "failed"
            state["message"] = "Binary pvserver tidak ditemukan."
            state["error"] = (
                "Binary pvserver tidak ditemukan. Atur environment variable PVSERVER_BINARY."
            )
            _save_state(state)
            return _state_response(state)

        if not _port_available(port):
            state["status"] = "failed"
            state["message"] = f"Port {port} sedang digunakan proses lain."
            state["error"] = state["message"]
            _save_state(state)
            return _state_response(state)

        command, render_backend, render_warning = _build_server_command(binary, port)
        server_version = _server_version(binary)
        environment = os.environ.copy()
        software_rendering = (
            render_backend.startswith("Xvfb")
            or render_backend in {"OSMESA", "Offscreen (belum terverifikasi)"}
        )
        if software_rendering:
            environment.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
            environment.setdefault("VTK_DISABLE_OSPRAY", "1")
            environment.setdefault("VTK_DISABLE_VISRTX", "1")
            software_threads = os.environ.get("PVSERVER_SOFTWARE_THREADS", "4").strip()
            try:
                software_thread_count = max(1, min(64, int(software_threads)))
            except ValueError:
                software_thread_count = 4
            environment.setdefault("LP_NUM_THREADS", str(software_thread_count))

        _ensure_runtime_root()

        try:
            _log_path().write_text("", encoding="utf-8")
            with _log_path().open("a", encoding="utf-8") as log_handle:
                os.chmod(_log_path(), 0o600)
                log_handle.write(f"$ cd {CASE_ROOT}\n")
                command_environment = []
                for variable in (
                    "LIBGL_ALWAYS_SOFTWARE",
                    "VTK_DISABLE_OSPRAY",
                    "VTK_DISABLE_VISRTX",
                    "LP_NUM_THREADS",
                ):
                    if variable in environment:
                        command_environment.append(f"{variable}={shlex.quote(environment[variable])}")
                environment_prefix = " ".join(command_environment)
                log_handle.write(f"$ {environment_prefix} {shlex.join(command)}\n".replace("$  ", "$ "))
                log_handle.write(f"[CASE] Target file: {CASE_FILE}\n")
                log_handle.write(f"[RENDER] Backend: {render_backend}\n")
                if software_rendering:
                    log_handle.write("[RENDER] Optional OSPRay/VisRTX ray tracing disabled.\n")
                if render_warning:
                    log_handle.write(f"[WARNING] {render_warning}\n")
                log_handle.write("[SYSTEM] Menyiapkan pvserver...\n")
                log_handle.flush()

                process = subprocess.Popen(
                    command,
                    cwd=CASE_ROOT,
                    env=environment,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except OSError as exc:
            state["status"] = "failed"
            state["message"] = "Gagal menjalankan pvserver."
            state["error"] = f"{state['message']} {exc}"
            _append_log(f"[ERROR] {state['error']}")
            _save_state(state)
            return _state_response(state)

        state.update(
            {
                "status": "starting",
                "running": True,
                "pid": process.pid,
                "server_version": server_version,
                "render_backend": render_backend,
                "render_warning": render_warning,
                "started_at": _utc_now(),
                "message": "pvserver sedang disiapkan.",
            }
        )
        state.pop("error", None)
        _save_state(state)

        watcher = threading.Thread(
            target=_watch_process,
            args=(process,),
            daemon=True,
            name=f"pvserver-watch-{process.pid}",
        )
        watcher.start()
        return _state_response(state)


def stop_server():
    with _manager_lock():
        state = _refresh_state(_load_state())
        pid = state.get("pid")

        if not state.get("running") or not _state_process_alive(state):
            if state.get("status") == "finalizing" and pid:
                state = _finalize_exited_state(state)
            elif state.get("status") not in {"failed", "idle"}:
                state["status"] = "stopped"
                state["message"] = "Remote ParaView sudah berhenti."
                state["running"] = False
                state["pid"] = None
                state["stop_requested"] = False
            _save_state(state)
            return _state_response(state)

        state["status"] = "stopping"
        state["stop_requested"] = True
        state["stop_failed"] = False
        state["message"] = "Menghentikan pvserver..."
        _save_state(state)
        _append_log("[SYSTEM] Permintaan stop diterima.")

        signal_errors = []
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except (PermissionError, OSError) as exc:
            signal_errors.append(str(exc))

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and _pid_exists(pid):
            time.sleep(0.1)

        if _pid_exists(pid):
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except (PermissionError, OSError) as exc:
                signal_errors.append(str(exc))

            kill_deadline = time.monotonic() + 2
            while time.monotonic() < kill_deadline and _pid_exists(pid):
                time.sleep(0.1)

        state = _load_state()
        if state.get("pid") == pid:
            if _pid_exists(pid):
                detail = f" ({'; '.join(signal_errors)})" if signal_errors else ""
                state["running"] = True
                state["stop_requested"] = False
                state["stop_failed"] = True
                state["status"] = "failed"
                state["message"] = "pvserver masih hidup dan gagal dihentikan."
                state["error"] = f"{state['message']}{detail}"
                _append_log(f"[ERROR] {state['error']}")
            else:
                state = _finalize_exited_state(state)
            _save_state(state)

        return _state_response(_refresh_state(state))

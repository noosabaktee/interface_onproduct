"""Case-root bounded terminal execution.

This module intentionally keeps one command session per Flask app. It is meant
for operational OpenFOAM commands while keeping the web application directory
out of reach.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
from pathlib import Path, PurePosixPath


class SandboxTerminalError(ValueError):
    """Error yang aman untuk ditampilkan di halaman Terminal."""


class SandboxTerminal:
    MAX_COMMAND_LENGTH = 4000
    MAX_LINES = 600
    _WINDOWS_DRIVE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z]:[\\/]")
    _LOCATION_COMMAND = re.compile(
        r"(^|[;&|()\s])(?:cd|chdir|pushd|popd|set-location|sl)(?=$|[;&|()\s])",
        re.IGNORECASE,
    )
    _NESTED_SHELL = re.compile(
        r"(^|[;&|()\s])(?:powershell(?:\.exe)?|pwsh|cmd(?:\.exe)?|wsl)(?=$|[;&|()\s])",
        re.IGNORECASE,
    )
    _INLINE_INTERPRETER = re.compile(
        r"(^|[;&|()\s])(?:python(?:\d(?:\.\d)?)?|py|perl|ruby|node)(?=$|[;&|()\s]).*?(^|\s)-(?:c|e)(?=$|\s)",
        re.IGNORECASE,
    )

    def __init__(self, case_root):
        self.case_root = Path(case_root).resolve()
        self._lock = threading.Lock()
        self._state = {
            "cwd": PurePosixPath(),
            "previous_cwd": PurePosixPath(),
            "running": False,
            "returncode": None,
            "status": "idle",
            "lines": [
                f"Case root: {self.case_root}",
                "Terminal siap. Semua command dijalankan dari folder case aktif.",
            ],
            "process": None,
            "last_command": "",
        }

    def start(self, command):
        command = str(command or "").strip()
        if not command:
            return self.snapshot()
        if len(command) > self.MAX_COMMAND_LENGTH:
            raise SandboxTerminalError("Command terlalu panjang.")
        if "\x00" in command or "\n" in command or "\r" in command:
            raise SandboxTerminalError("Jalankan satu command per eksekusi.")

        with self._lock:
            if self._state["running"]:
                raise SandboxTerminalError("Masih ada command yang berjalan.")

        builtin_result = self._handle_builtin(command)
        if builtin_result:
            return self.snapshot()

        self._validate_command(command)
        with self._lock:
            cwd = self._current_path_unlocked()
            self._state["running"] = True
            self._state["returncode"] = None
            self._state["status"] = "running"
            self._state["last_command"] = command
            self._append_unlocked(f"{self.prompt_unlocked()} {command}")

        thread = threading.Thread(
            target=self._run_subprocess,
            args=(command, cwd),
            daemon=True,
        )
        thread.start()
        return self.snapshot()

    def stop(self):
        with self._lock:
            process = self._state.get("process")
            if not self._state["running"] or process is None:
                raise SandboxTerminalError("Tidak ada command yang sedang berjalan.")
            self._append_unlocked("^C")

        self._terminate_process(process)
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            cwd = self._state["cwd"].as_posix() or "."
            return {
                "case_root": str(self.case_root),
                "cwd": cwd,
                "prompt": self.prompt_unlocked(),
                "running": self._state["running"],
                "returncode": self._state["returncode"],
                "status": self._state["status"],
                "lines": list(self._state["lines"][-self.MAX_LINES :]),
                "last_command": self._state["last_command"],
            }

    def prompt_unlocked(self):
        cwd = self._state["cwd"].as_posix()
        return f"case:/{cwd} $" if cwd and cwd != "." else "case:/ $"

    def _handle_builtin(self, command):
        lowered = command.casefold()
        if lowered in {"clear", "cls"}:
            with self._lock:
                self._state["lines"] = []
                self._state["returncode"] = 0
                self._state["status"] = "completed"
            return True

        if lowered in {"pwd", "cwd"}:
            with self._lock:
                self._append_unlocked(f"{self.prompt_unlocked()} {command}")
                self._append_unlocked(str(self._current_path_unlocked()))
                self._state["returncode"] = 0
                self._state["status"] = "completed"
            return True

        if lowered in {"exit", "logout"}:
            with self._lock:
                self._append_unlocked(f"{self.prompt_unlocked()} {command}")
                self._append_unlocked("Sesi web terminal tetap aktif.")
                self._state["returncode"] = 0
                self._state["status"] = "completed"
            return True

        match = re.fullmatch(r"(?:cd|chdir|set-location|sl)\s*(.*)", command, re.IGNORECASE)
        if match:
            target = match.group(1).strip().strip("\"'")
            self._change_directory(target or ".")
            return True

        return False

    def _change_directory(self, target):
        if any(separator in target for separator in (";", "&", "|", "`")):
            raise SandboxTerminalError("Gunakan command cd terpisah tanpa operator shell.")

        with self._lock:
            self._append_unlocked(f"{self.prompt_unlocked()} cd {target}")
            if target == "-":
                path = self.case_root.joinpath(*self._state["previous_cwd"].parts).resolve(strict=False)
            else:
                path = self._resolve_inside_unlocked(target, allow_root=True, allow_parent=True)
            if not path.exists():
                raise SandboxTerminalError("Folder tujuan tidak ditemukan di dalam case.")
            if not path.is_dir() or path.is_symlink():
                raise SandboxTerminalError("Target cd harus folder biasa di dalam case.")
            previous_cwd = self._state["cwd"]
            try:
                path.relative_to(self.case_root)
            except ValueError as exc:
                raise SandboxTerminalError("Path harus berada di dalam folder case.") from exc
            self._state["cwd"] = PurePosixPath(path.relative_to(self.case_root).as_posix())
            self._state["previous_cwd"] = previous_cwd
            self._state["returncode"] = 0
            self._state["status"] = "completed"

    def _validate_command(self, command):
        stripped = command.strip()
        if ".." in stripped:
            raise SandboxTerminalError("Path parent '..' tidak diizinkan.")
        if "~" in stripped:
            raise SandboxTerminalError("Path home '~' tidak diizinkan.")
        if self._WINDOWS_DRIVE.search(stripped) or "\\\\" in stripped:
            raise SandboxTerminalError("Path absolut Windows/UNC tidak diizinkan.")
        if re.search(r"(^|[\s=:'\"])/(?![A-Za-z])", stripped):
            raise SandboxTerminalError("Path absolut tidak diizinkan.")
        if re.search(r"(\$env:|\$\{|\$HOME|\$PWD|%[A-Za-z_][A-Za-z0-9_]*%)", stripped, re.IGNORECASE):
            raise SandboxTerminalError("Ekspansi environment path tidak diizinkan.")
        if self._LOCATION_COMMAND.search(stripped):
            raise SandboxTerminalError("Gunakan cd sebagai command terpisah agar folder tetap dibatasi.")
        if self._NESTED_SHELL.search(stripped):
            raise SandboxTerminalError("Nested shell tidak diizinkan dari web terminal.")
        if self._INLINE_INTERPRETER.search(stripped):
            raise SandboxTerminalError("Interpreter inline (-c/-e) tidak diizinkan.")

    def _run_subprocess(self, command, cwd):
        try:
            process = subprocess.Popen(
                self._shell_command(command),
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            with self._lock:
                self._state["process"] = process

            if process.stdout:
                for line in process.stdout:
                    with self._lock:
                        self._append_unlocked(line.rstrip())

            returncode = process.wait()
            with self._lock:
                self._state["running"] = False
                self._state["returncode"] = returncode
                self._state["process"] = None
                self._state["status"] = "completed" if returncode == 0 else "failed"
                self._append_unlocked(f"[exit {returncode}]")
        except Exception as exc:
            with self._lock:
                self._state["running"] = False
                self._state["returncode"] = -1
                self._state["process"] = None
                self._state["status"] = "failed"
                self._append_unlocked(f"Error: {exc}")

    def _shell_command(self, command):
        if os.name == "nt":
            return [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ]
        shell = os.environ.get("SHELL", "/bin/bash")
        return [shell, "-lc", command]

    def _current_path_unlocked(self):
        return self.case_root.joinpath(*self._state["cwd"].parts).resolve(strict=False)

    def _resolve_inside_unlocked(self, value, allow_root=False, allow_parent=False):
        raw = str(value or "").replace("\\", "/").strip()
        if not raw:
            raw = "."
        pure = PurePosixPath(raw)
        parts = tuple(part for part in pure.parts if part not in {"", "."})
        if pure.is_absolute() or any(
            (part == ".." and not allow_parent) or ":" in part or "\x00" in part
            for part in parts
        ):
            raise SandboxTerminalError("Path harus berada di dalam folder case.")
        if not parts and not allow_root:
            raise SandboxTerminalError("Path wajib diisi.")

        candidate = self._current_path_unlocked().joinpath(*parts).resolve(strict=False)
        try:
            candidate.relative_to(self.case_root)
        except ValueError as exc:
            raise SandboxTerminalError("Path harus berada di dalam folder case.") from exc
        return candidate

    def _append_unlocked(self, line):
        self._state["lines"].append(str(line))
        if len(self._state["lines"]) > self.MAX_LINES * 2:
            self._state["lines"] = self._state["lines"][-self.MAX_LINES :]

    def _terminate_process(self, process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            return

        try:
            os.killpg(process.pid, signal.SIGINT)
            process.wait(timeout=8)
            return
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            pass

        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

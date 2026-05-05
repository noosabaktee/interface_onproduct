import subprocess
import sys
import threading
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


COMMANDS = {
    "meshing": [
        sys.executable,
        "-u",
        "-c",
        (
            "import time\n"
            "steps=['blockMesh','snappyHexMesh','checkMesh']\n"
            "for i, step in enumerate(steps, 1):\n"
            "    print(f'[{i}/{len(steps)}] Running {step} ...', flush=True)\n"
            "    time.sleep(1)\n"
            "    print(f'{step} completed', flush=True)\n"
            "print('Meshing finished successfully.', flush=True)\n"
        ),
    ],
    "solver": [
        sys.executable,
        "-u",
        "-c",
        (
            "import time\n"
            "for i in range(1, 8):\n"
            "    print(f'Time = {i * 0.5:.1f} s | residual T = {1/i:.4f}', flush=True)\n"
            "    time.sleep(1)\n"
            "print('Solver finished successfully.', flush=True)\n"
        ),
    ],
}


_states = {
    key: {"running": False, "returncode": None, "lines": []}
    for key in COMMANDS
}
_lock = threading.Lock()


def start_command(task_key):
    with _lock:
        state = _states[task_key]
        if state["running"]:
            return _copy_state(task_key)

        state["running"] = True
        state["returncode"] = None
        state["lines"] = [f"$ {' '.join(COMMANDS[task_key])}"]

    thread = threading.Thread(target=_run_command, args=(task_key,), daemon=True)
    thread.start()
    return get_command_state(task_key)


def get_command_state(task_key):
    with _lock:
        return _copy_state(task_key)


def _run_command(task_key):
    try:
        process = subprocess.Popen(
            COMMANDS[task_key],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        if process.stdout:
            for line in process.stdout:
                _append_line(task_key, line.rstrip())

        returncode = process.wait()
        with _lock:
            _states[task_key]["running"] = False
            _states[task_key]["returncode"] = returncode
            _states[task_key]["lines"].append(f"Process exited with code {returncode}.")
    except Exception as exc:
        with _lock:
            _states[task_key]["running"] = False
            _states[task_key]["returncode"] = -1
            _states[task_key]["lines"].append(f"Error: {exc}")


def _append_line(task_key, line):
    with _lock:
        _states[task_key]["lines"].append(line)


def _copy_state(task_key):
    state = _states[task_key]
    return {
        "running": state["running"],
        "returncode": state["returncode"],
        "lines": list(state["lines"][-300:]),
    }

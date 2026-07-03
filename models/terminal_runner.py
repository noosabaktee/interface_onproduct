import subprocess
import sys
import os
import signal
import threading
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_ROOT = PROJECT_ROOT.parent / "sprayDryer-6.0.0-onProduct-Trial02"


MESHING_STEPS = [
    ("Cleaning old mesh/run", "rm -rf processor* constant/polyMesh log.*", 10),
    ("BlockMesh", "blockMesh", 25),
    ("Surface Feature Extract", "surfaceFeatureExtract", 40),
    ("SnappyHexMesh", "snappyHexMesh -overwrite", 60),
    ("CheckMesh", "checkMesh", 80),
    ("DecomposePar", "decomposePar -force", 100),
]


COMMANDS = {
    "meshing": [
        sys.executable,
        "-u",
        "-c",
        (
            "import subprocess, sys, time\n"
            "case_root = r'" + str(CASE_ROOT) + "'\n"
            "steps = [\n"
            "    ('Cleaning old mesh/run', 'rm -rf processor* constant/polyMesh log.*'),\n"
            "    ('BlockMesh', 'blockMesh'),\n"
            "    ('Surface Feature Extract', 'surfaceFeatureExtract'),\n"
            "    ('SnappyHexMesh', 'snappyHexMesh -overwrite'),\n"
            "    ('CheckMesh', 'checkMesh'),\n"
            "    ('DecomposePar', 'decomposePar -force'),\n"
            "]\n"
            "total_steps = len(steps)\n"
            "for i, (name, cmd) in enumerate(steps, 1):\n"
            "    print(f'[{i}/{total_steps}] {name}...', flush=True)\n"
            "    result = subprocess.run(cmd, shell=True, cwd=case_root, capture_output=True, text=True)\n"
            "    if result.stdout: print(result.stdout.rstrip(), flush=True)\n"
            "    if result.stderr: print(result.stderr.rstrip(), flush=True)\n"
            "    if result.returncode != 0:\n"
            "        print(f'Error in {name}: {result.returncode}', flush=True)\n"
            "        sys.exit(result.returncode)\n"
            "    print(f'{name} completed.', flush=True)\n"
            "print('Meshing finished successfully.', flush=True)\n"
        ),
    ],
    "solver": [
        sys.executable,
        "-u",
        "-c",
        (
            "import subprocess, sys, os\n"
            "from pathlib import Path\n"
            "case_root = Path(r'" + str(CASE_ROOT) + "')\n"
            "decompose_dict = case_root / 'system' / 'decomposeParDict'\n"
            "np = 4\n"
            "try:\n"
            "    with open(decompose_dict, 'r') as f:\n"
            "        for line in f:\n"
            "            if 'numberOfSubdomains' in line:\n"
            "                parts = line.split()\n"
            "                if len(parts) > 1:\n"
            "                    np = int(parts[1].rstrip(';'))\n"
            "                    break\n"
            "except:\n"
            "    pass\n"
            "os.environ['OMPI_ALLOW_RUN_AS_ROOT'] = '1'\n"
            "os.environ['OMPI_ALLOW_RUN_AS_ROOT_CONFIRM'] = '1'\n"
            "cmd = f'mpirun --allow-run-as-root --oversubscribe -np {np} buoyantPimpleFoam -parallel'\n"
            "print(f'Running solver with {np} processors...', flush=True)\n"
            "process = subprocess.Popen(cmd, shell=True, cwd=case_root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)\n"
            "if process.stdout:\n"
            "    for line in process.stdout:\n"
            "        print(line.rstrip(), flush=True)\n"
            "returncode = process.wait()\n"
            "if returncode != 0:\n"
            "    print(f'Solver error: {returncode}', flush=True)\n"
            "    sys.exit(returncode)\n"
            "print('Solver finished successfully.', flush=True)\n"
        ),
    ],
}


_states = {
    key: {
        "running": False,
        "returncode": None,
        "lines": [],
        "progress": 0,
        "process": None,
        "current_step": 0,
        "stop_requested": False,
        "cancel_requested": False,
        "status": "idle",
        "resume_available": False,
    }
    for key in COMMANDS
}
_lock = threading.Lock()


def start_command(task_key):
    with _lock:
        # Check if other task is running
        other_key = "solver" if task_key == "meshing" else "meshing"
        if _states[other_key]["running"]:
            return {"error": f"Cannot start {task_key} while {other_key} is running."}

        state = _states[task_key]
        if state["running"]:
            return _copy_state(task_key)

        if task_key == "solver" and not _meshing_ready_unlocked():
            response = _copy_state(task_key)
            response["error"] = "Meshing harus selesai sebelum menjalankan solver."
            return response

        state["running"] = True
        state["returncode"] = None
        state["stop_requested"] = False
        state["cancel_requested"] = False
        state["status"] = "running"
        if state["resume_available"]:
            if task_key == "meshing":
                next_step = state["current_step"] + 1
                state["lines"].append(f"Resuming meshing from step {next_step}/{len(MESHING_STEPS)}...")
            else:
                state["lines"].append("Resuming from latest checkpoint/time directory...")
        else:
            state["lines"] = [f"$ {' '.join(COMMANDS[task_key])}"]
            state["progress"] = 0
            state["current_step"] = 0

    thread = threading.Thread(target=_run_command, args=(task_key,), daemon=True)
    thread.start()
    return get_command_state(task_key)


def stop_command(task_key):
    with _lock:
        state = _states[task_key]
        if not state["running"]:
            return False
        process = state.get("process")
        state["stop_requested"] = True
        state["lines"].append("Stop requested. Writing latest checkpoint if supported...")

    if process and process.poll() is None:
        _terminate_process_group(process)

    with _lock:
        state = _states[task_key]
        state["running"] = False
        state["returncode"] = -15
        state["status"] = "stopped"
        state["resume_available"] = task_key in {"meshing", "solver"}
        state["process"] = None
        state["lines"].append(
            "Solver stopped. Click Resume to continue from the latest checkpoint."
            if task_key == "solver"
            else "Meshing stopped. Click Resume to continue from the interrupted step."
        )
        return True


def cancel_command(task_key):
    with _lock:
        state = _states[task_key]
        if not state["running"]:
            return False
        process = state.get("process")
        state["cancel_requested"] = True
        state["lines"].append("Cancel requested. Terminating process without resume.")

    if process and process.poll() is None:
        _terminate_process_group(process)

    with _lock:
        state = _states[task_key]
        state["running"] = False
        state["returncode"] = -15
        state["status"] = "cancelled"
        state["resume_available"] = False
        state["process"] = None
        state["lines"].append("Process cancelled.")
        return True


def get_command_state(task_key):
    with _lock:
        return _copy_state(task_key)


def is_meshing_ready():
    with _lock:
        return _meshing_ready_unlocked()


def _run_command(task_key):
    if task_key == "meshing":
        _run_meshing_command()
        return

    try:
        process = subprocess.Popen(
            COMMANDS[task_key],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        with _lock:
            _states[task_key]["process"] = process
            stop_requested = _states[task_key]["stop_requested"]
            cancel_requested = _states[task_key]["cancel_requested"]

        if (stop_requested or cancel_requested) and process.poll() is None:
            _terminate_process_group(process)

        if process.stdout:
            for line in process.stdout:
                line = line.rstrip()
                _append_line(task_key, line)
                # Update progress based on steps
                if task_key == "meshing":
                    if "[1/" in line:
                        _update_progress(task_key, 10)
                    elif "[2/" in line:
                        _update_progress(task_key, 25)
                    elif "[3/" in line:
                        _update_progress(task_key, 40)
                    elif "[4/" in line:
                        _update_progress(task_key, 60)
                    elif "[5/" in line:
                        _update_progress(task_key, 80)
                    elif "[6/" in line:
                        _update_progress(task_key, 100)
                elif task_key == "solver":
                    if "Running solver" in line:
                        _update_progress(task_key, 50)
                    elif "Solver finished" in line:
                        _update_progress(task_key, 100)

        returncode = process.wait()
        with _lock:
            stopped_by_user = _states[task_key]["stop_requested"]
            cancelled_by_user = _states[task_key]["cancel_requested"]
            _states[task_key]["running"] = False
            _states[task_key]["returncode"] = returncode
            _states[task_key]["process"] = None
            if cancelled_by_user:
                _states[task_key]["status"] = "cancelled"
                _states[task_key]["resume_available"] = False
            elif stopped_by_user:
                _states[task_key]["status"] = "stopped"
                _states[task_key]["resume_available"] = task_key in {"meshing", "solver"}
            elif returncode == 0:
                _states[task_key]["status"] = "completed"
                _states[task_key]["resume_available"] = False
                _states[task_key]["lines"].append("Process completed successfully.")
            else:
                _states[task_key]["status"] = "failed"
                _states[task_key]["lines"].append(f"Process failed with code {returncode}.")
    except Exception as exc:
        with _lock:
            _states[task_key]["running"] = False
            _states[task_key]["returncode"] = -1
            _states[task_key]["process"] = None
            _states[task_key]["status"] = "failed"
            _states[task_key]["lines"].append(f"Error: {exc}")


def _run_meshing_command():
    task_key = "meshing"
    try:
        with _lock:
            start_index = _states[task_key]["current_step"]

        for index in range(start_index, len(MESHING_STEPS)):
            name, cmd, progress = MESHING_STEPS[index]

            with _lock:
                if _states[task_key]["stop_requested"] or _states[task_key]["cancel_requested"]:
                    break
                _states[task_key]["current_step"] = index
                _states[task_key]["lines"].append(f"[{index + 1}/{len(MESHING_STEPS)}] {name}...")

            process = subprocess.Popen(
                cmd,
                shell=True,
                cwd=CASE_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            with _lock:
                _states[task_key]["process"] = process
                should_stop = _states[task_key]["stop_requested"] or _states[task_key]["cancel_requested"]

            if should_stop and process.poll() is None:
                _terminate_process_group(process)

            if process.stdout:
                for line in process.stdout:
                    _append_line(task_key, line.rstrip())

            returncode = process.wait()
            with _lock:
                _states[task_key]["process"] = None
                stopped_by_user = _states[task_key]["stop_requested"]
                cancelled_by_user = _states[task_key]["cancel_requested"]

            if stopped_by_user or cancelled_by_user:
                with _lock:
                    _finish_interrupted_meshing(cancelled_by_user)
                return

            if returncode != 0:
                with _lock:
                    _states[task_key]["running"] = False
                    _states[task_key]["returncode"] = returncode
                    _states[task_key]["status"] = "failed"
                    _states[task_key]["resume_available"] = False
                    _states[task_key]["lines"].append(f"Error in {name}: {returncode}")
                return

            with _lock:
                _states[task_key]["current_step"] = index + 1
                _states[task_key]["progress"] = progress
                _states[task_key]["lines"].append(f"{name} completed.")

        with _lock:
            if _states[task_key]["cancel_requested"]:
                _finish_interrupted_meshing(True)
                return

            if _states[task_key]["stop_requested"]:
                _finish_interrupted_meshing(False)
                return

            _states[task_key]["running"] = False
            _states[task_key]["returncode"] = 0
            _states[task_key]["status"] = "completed"
            _states[task_key]["resume_available"] = False
            _states[task_key]["current_step"] = 0
            _states[task_key]["lines"].append("Meshing finished successfully.")
            _states[task_key]["lines"].append("Process completed successfully.")
    except Exception as exc:
        with _lock:
            _states[task_key]["running"] = False
            _states[task_key]["returncode"] = -1
            _states[task_key]["process"] = None
            _states[task_key]["status"] = "failed"
            _states[task_key]["resume_available"] = False
            _states[task_key]["lines"].append(f"Error: {exc}")


def _finish_interrupted_meshing(cancelled):
    _states["meshing"]["running"] = False
    _states["meshing"]["returncode"] = -15
    _states["meshing"]["status"] = "cancelled" if cancelled else "stopped"
    _states["meshing"]["resume_available"] = not cancelled


def _append_line(task_key, line):
    with _lock:
        _states[task_key]["lines"].append(line)


def _update_progress(task_key, progress):
    with _lock:
        _states[task_key]["progress"] = progress


def _copy_state(task_key):
    state = _states[task_key]
    return {
        "running": state["running"],
        "returncode": state["returncode"],
        "lines": list(state["lines"][-300:]),
        "progress": state["progress"],
        "status": state["status"],
        "resume_available": state["resume_available"],
        "meshing_ready": _meshing_ready_unlocked(),
    }


def _meshing_ready_unlocked():
    processor_count = _load_processor_count()
    required_mesh_files = {"boundary", "faces", "neighbour", "owner", "points"}

    for index in range(processor_count):
        mesh_dir = CASE_ROOT / f"processor{index}" / "constant" / "polyMesh"
        if not mesh_dir.is_dir():
            return False

        if not all((mesh_dir / filename).is_file() for filename in required_mesh_files):
            return False

    return True


def _load_processor_count(default=1):
    decompose_dict = CASE_ROOT / "system" / "decomposeParDict"
    if not decompose_dict.exists():
        return default

    try:
        for line in decompose_dict.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("numberOfSubdomains"):
                parts = stripped.rstrip(";").split()
                if len(parts) >= 2:
                    return max(1, int(parts[1]))
    except (OSError, ValueError):
        pass

    return default


def _terminate_process_group(process):
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
        return
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

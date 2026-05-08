import subprocess
import sys
import threading
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_ROOT = PROJECT_ROOT.parent / "sprayDryer-6.0.0-onProduct-Trial02"


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
            "result = subprocess.run(cmd, shell=True, cwd=case_root, capture_output=True, text=True)\n"
            "if result.stdout: print(result.stdout.rstrip(), flush=True)\n"
            "if result.stderr: print(result.stderr.rstrip(), flush=True)\n"
            "if result.returncode != 0:\n"
            "    print(f'Solver error: {result.returncode}', flush=True)\n"
            "    sys.exit(result.returncode)\n"
            "print('Solver finished successfully.', flush=True)\n"
        ),
    ],
}


_states = {
    key: {"running": False, "returncode": None, "lines": [], "progress": 0}
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

        state["running"] = True
        state["returncode"] = None
        state["lines"] = [f"$ {' '.join(COMMANDS[task_key])}"]
        state["progress"] = 0

    thread = threading.Thread(target=_run_command, args=(task_key,), daemon=True)
    thread.start()
    return get_command_state(task_key)


def cancel_command(task_key):
    with _lock:
        state = _states[task_key]
        if not state["running"]:
            return False
        # Note: In a real implementation, we'd need to track the process and kill it
        # For now, just mark as not running
        state["running"] = False
        state["returncode"] = -1
        state["lines"].append("Process cancelled.")
        return True


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
            _states[task_key]["running"] = False
            _states[task_key]["returncode"] = returncode
            if returncode == 0:
                _states[task_key]["lines"].append("Process completed successfully.")
            else:
                _states[task_key]["lines"].append(f"Process failed with code {returncode}.")
    except Exception as exc:
        with _lock:
            _states[task_key]["running"] = False
            _states[task_key]["returncode"] = -1
            _states[task_key]["lines"].append(f"Error: {exc}")


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
    }

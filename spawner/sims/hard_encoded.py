from __future__ import annotations

import base64
import os
import pathlib
import subprocess
import tempfile
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

PROC = "python3"  # No typo — detection must come purely from behavior

BENIGN_PAYLOAD = base64.b64encode(b"print('system check ok')").decode()


def drop_encoded_blob() -> pathlib.Path:
    blob = base64.b64encode(os.urandom(512)).decode()
    path = pathlib.Path(f"/tmp/.enc_{int(time.time())}.b64")
    path.write_text(blob)
    log(PROC, f"Encoded blob staged: {path}")
    return path


def fileless_exec_sim() -> None:
    # Creates and immediately deletes a .py file — rapid create/delete is detectable via auditd
    try:
        fd, path = tempfile.mkstemp(suffix=".py", dir="/tmp", prefix=".")
        payload = f"# auto-generated\nimport os\nprint(os.uname())\n"
        os.write(fd, payload.encode())
        os.close(fd)
        time.sleep(random.uniform(0.5, 2.0))
        os.unlink(path)
        log(PROC, f"Fileless exec sim: {path} created and deleted")
    except Exception:
        pass


def encoded_subprocess() -> None:
    # Spawns: python3 -c exec(b64decode(...)) — visible in ps for a few seconds
    cmd = f"exec(__import__('base64').b64decode('{BENIGN_PAYLOAD}').decode())"
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log(PROC, f"Encoded subprocess spawned: PID {proc.pid}")
        proc.wait(timeout=5)
    except Exception:
        pass


def read_self_maps() -> None:
    # Self-inspection — common in AV-aware malware
    try:
        maps = pathlib.Path("/proc/self/maps").read_text()
        log(PROC, f"Self maps read: {len(maps.splitlines())} regions")
    except Exception:
        pass


def main() -> None:
    set_proc_name(PROC)
    log(PROC, "Starting encoded payload handler")

    while True:
        drop_encoded_blob()
        fileless_exec_sim()

        time.sleep(jitter(30.0))

        encoded_subprocess()

        if random.random() < 0.2:
            read_self_maps()

        time.sleep(jitter(90.0))


main()

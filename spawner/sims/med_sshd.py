from __future__ import annotations

import pathlib
import socket
import subprocess
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

# Legitimate name (sshd) but running from wrong location — major IOC
PROC = "sshd"
FAKE_CONFIG = pathlib.Path("/tmp/.sshd_config")

SSH_BANNER = b"SSH-2.0-OpenSSH_8.4p1 Debian-5+deb11u3\r\n"


def write_fake_config() -> None:
    try:
        FAKE_CONFIG.write_text(
            "Port 2222\n"
            "PermitRootLogin yes\n"
            "PasswordAuthentication yes\n"
            "AuthorizedKeysFile /tmp/.authorized_keys\n"
            "PermitEmptyPasswords yes\n"
            "Banner /tmp/.motd\n"
        )
        log(PROC, f"Wrote fake config to {FAKE_CONFIG}")
    except Exception:
        pass


def scan_localhost() -> None:
    # Port scanning localhost — sshd has no reason to do this
    ports_to_scan = random.sample(range(1, 1025), 20)
    open_ports = []
    for port in ports_to_scan:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.1)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                open_ports.append(port)
            s.close()
        except Exception:
            pass
    if open_ports:
        log(PROC, f"Open ports found: {open_ports}")


def fake_listener() -> None:
    # Bind on 2222 (non-standard SSH port)
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", 2222))
        srv.listen(1)
        srv.settimeout(0.5)
        log(PROC, "Fake SSH listener on :2222")
        while True:
            try:
                conn, addr = srv.accept()
                conn.sendall(SSH_BANNER)
                log(PROC, f"SSH connection from {addr[0]}:{addr[1]}")
                conn.close()
            except socket.timeout:
                pass
            time.sleep(0.1)
    except Exception as e:
        log(PROC, f"Listener failed: {e}")
        # Fall back to sleeping loop
        while True:
            scan_localhost()
            time.sleep(jitter(45.0))


def main() -> None:
    set_proc_name(PROC)
    write_fake_config()
    log(PROC, "sshd: server listening on 0.0.0.0 port 2222")

    import threading
    t = threading.Thread(target=fake_listener, daemon=True)
    t.start()

    while True:
        scan_localhost()
        # Read SSH host keys (legitimate sshd behavior but wrong location)
        for path in ["/tmp/.ssh_host_rsa_key", "/tmp/.ssh_host_ed25519_key"]:
            try:
                pathlib.Path(path).read_bytes()
            except Exception:
                pass
        time.sleep(jitter(30.0))


main()

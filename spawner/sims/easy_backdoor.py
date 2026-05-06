from __future__ import annotations

import socket
import threading
import time
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log

PROC = "backdoor"
PORT = 4444
BANNER = b"\r\n[BACKDOOR v2.3.1] Connection established. Type 'help' for commands.\r\n> "


def handle(conn: socket.socket, addr: tuple) -> None:
    log(PROC, f"Connection from {addr[0]}:{addr[1]}")
    try:
        conn.sendall(BANNER)
        while True:
            data = conn.recv(1024)
            if not data:
                break
            cmd = data.decode(errors="ignore").strip()
            log(PROC, f"Received cmd: {cmd}")
            if cmd == "help":
                conn.sendall(b"Commands: sysinfo, download, upload, shell, exit\r\n> ")
            elif cmd == "sysinfo":
                import platform, os
                info = f"OS:{platform.system()} User:{os.getlogin()} Host:{platform.node()}\r\n"
                conn.sendall(info.encode() + b"> ")
            elif cmd == "exit":
                conn.sendall(b"Bye.\r\n")
                break
            else:
                conn.sendall(b"[*] Command queued for execution.\r\n> ")
    except Exception:
        pass
    finally:
        conn.close()
        log(PROC, f"Connection from {addr[0]}:{addr[1]} closed")


def main() -> None:
    set_proc_name(PROC)
    log(PROC, f"Starting backdoor listener on 0.0.0.0:{PORT}")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", PORT))
    except OSError as e:
        log(PROC, f"Bind failed: {e} — retrying on 4445")
        srv.bind(("0.0.0.0", 4445))
    srv.listen(5)
    log(PROC, f"Listening on port {PORT}")

    srv.settimeout(1.0)
    while True:
        try:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle, args=(conn, addr), daemon=True)
            t.start()
        except socket.timeout:
            pass
        time.sleep(0.1)


main()

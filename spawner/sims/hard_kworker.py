from __future__ import annotations

import os
import pathlib
import socket
import tempfile
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

# Real kworkers: no exe, no open FDs, no network, show as [kworker/0:2H] with brackets in ps
# This one: has exe (python3), network socket, open FDs — detectable via 'ss -p' or 'ls -la /proc/PID/exe'
PROC = "kworker/0:2H"
PORT_SCAN_FILE = pathlib.Path("/tmp/.kw_portscan")


def read_network_state() -> None:
    for path in ["/proc/net/tcp", "/proc/net/tcp6", "/proc/net/udp"]:
        try:
            content = pathlib.Path(path).read_text()
            conns = len(content.splitlines()) - 1
            log(PROC, f"Network state {path}: {conns} entries")
            PORT_SCAN_FILE.write_text(content[:4096])
        except Exception:
            pass


def proc_mem_probe() -> None:
    # Probe /proc/1/maps and /proc/1/environ — will fail without root but attempt is IOC
    for target in ["/proc/1/maps", "/proc/1/environ", "/proc/kcore"]:
        try:
            pathlib.Path(target).read_bytes()[:256]
            log(PROC, f"Read {target}")
        except PermissionError:
            log(PROC, f"Access denied: {target} (attempted)")
        except Exception:
            pass


def dns_tcp_beacon() -> None:
    # Real kworkers NEVER make network connections — this is the key IOC
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(("8.8.8.8", 53))
        # Send 20 bytes — simulates DNS-over-TCP C2
        s.sendall(b"\x00\x14" + os.urandom(18))
        log(PROC, "DNS-over-TCP beacon sent to 8.8.8.8:53")
        s.close()
    except Exception as e:
        log(PROC, f"Beacon failed: {e}")


def stage_and_delete() -> None:
    # Write then delete a fake payload — visible via auditd/inotify
    try:
        fake_elf = b"\x7fELF\x02\x01\x01\x00" + os.urandom(4088)
        fd, path = tempfile.mkstemp(prefix=".kw_", dir="/tmp")
        os.write(fd, fake_elf)
        os.close(fd)
        log(PROC, f"Staged payload: {path}")
        time.sleep(random.uniform(30, 60))
        os.unlink(path)
        log(PROC, f"Deleted payload: {path}")
    except Exception:
        pass


def main() -> None:
    set_proc_name(PROC)
    log(PROC, "kworker initialized")

    tick = 0
    while True:
        tick += 1
        # Very slow — one action every 8-15s to avoid standing out
        time.sleep(random.uniform(8, 15))

        match tick % 12:
            case 1:  read_network_state()
            case 3:  proc_mem_probe()
            case 6:  dns_tcp_beacon()
            case 9:  stage_and_delete()
            case _:  pass  # idle — looks like normal kworker


main()

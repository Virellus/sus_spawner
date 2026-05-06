from __future__ import annotations

import pathlib
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

# Typo: dbus-daem0n (zero) vs legitimate dbus-daemon
PROC = "dbus-daem0n"
DUMP_FILE = pathlib.Path("/tmp/.proc_dump")


def enumerate_procs() -> list[dict]:
    procs = []
    try:
        for pid_dir in pathlib.Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                cmdline = (pid_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="ignore").strip()
                status = (pid_dir / "status").read_text()
                name = ""
                ppid = ""
                uid = ""
                for line in status.splitlines():
                    if line.startswith("Name:"):
                        name = line.split()[1]
                    elif line.startswith("PPid:"):
                        ppid = line.split()[1]
                    elif line.startswith("Uid:"):
                        uid = line.split()[1]
                if cmdline:
                    procs.append({"pid": pid_dir.name, "name": name, "ppid": ppid, "uid": uid, "cmd": cmdline[:80]})
            except Exception:
                pass
    except Exception:
        pass
    return procs


def snoop_environ() -> None:
    # Read environment variables of other processes — highly suspicious for dbus
    try:
        pids = [d.name for d in pathlib.Path("/proc").iterdir() if d.name.isdigit()]
        sample = random.sample(pids, min(5, len(pids)))
        for pid in sample:
            try:
                env = pathlib.Path(f"/proc/{pid}/environ").read_bytes()
                if b"PASSWORD" in env or b"SECRET" in env or b"TOKEN" in env or b"KEY" in env:
                    log(PROC, f"Sensitive env var in PID {pid}")
            except Exception:
                pass
    except Exception:
        pass


def snoop_fds() -> None:
    # Check open file descriptors of other processes
    try:
        pids = [d.name for d in pathlib.Path("/proc").iterdir() if d.name.isdigit()]
        pid = random.choice(pids)
        fd_dir = pathlib.Path(f"/proc/{pid}/fd")
        fds = list(fd_dir.iterdir())
        log(PROC, f"PID {pid} has {len(fds)} open file descriptors")
    except Exception:
        pass


def main() -> None:
    set_proc_name(PROC)
    log(PROC, "dbus-daemon --system starting")

    while True:
        procs = enumerate_procs()
        log(PROC, f"Enumerated {len(procs)} processes")
        try:
            import json
            DUMP_FILE.write_text(json.dumps(procs[:50], indent=2))
        except Exception:
            pass

        snoop_environ()
        snoop_fds()

        # Read network connections
        try:
            tcp = pathlib.Path("/proc/net/tcp").read_text()
            tcp6 = pathlib.Path("/proc/net/tcp6").read_text()
            log(PROC, f"Network state: {len(tcp.splitlines())} TCP connections")
        except Exception:
            pass

        time.sleep(jitter(20.0))


main()

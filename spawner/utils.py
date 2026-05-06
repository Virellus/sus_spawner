from __future__ import annotations

import ctypes
import ctypes.util
import json
import pathlib
import random

PID_FILE = pathlib.Path("/tmp/.sus_spawner.pids")
LOG_DIR = pathlib.Path("/tmp")


def set_proc_name(name: str) -> None:
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        libc.prctl(15, name.encode()[:15], 0, 0, 0)
    except Exception:
        pass


def jitter(base: float, pct: float = 0.3) -> float:
    delta = base * pct
    return base + random.uniform(-delta, delta)


def log(name: str, msg: str) -> None:
    try:
        path = LOG_DIR / f".{name}.log"
        with path.open("a") as f:
            import datetime
            f.write(f"[{datetime.datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


def write_pids(pids: dict[str, int]) -> None:
    PID_FILE.write_text(json.dumps(pids, indent=2))


def read_pids() -> dict[str, int]:
    if not PID_FILE.exists():
        return {}
    try:
        return json.loads(PID_FILE.read_text())
    except Exception:
        return {}

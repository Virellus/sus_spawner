from __future__ import annotations

import os
import pathlib
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

PROC = "keylogger"
KEYLOG_FILE = pathlib.Path("/tmp/.keylog")
CRED_FILE = pathlib.Path("/tmp/.captured_creds")

FAKE_CREDS = [
    "user=admin password=Summer2024!",
    "user=root password=P@ssw0rd123",
    "sudo password captured: hunter2",
    "ssh passphrase: correct-horse-battery-staple",
    "wifi_psk=MyHomeNetwork2024",
]

FAKE_KEYS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 \n\t"


def capture_loop() -> None:
    # Try real /dev/input devices first, fall back to simulated capture
    input_devs = list(pathlib.Path("/dev/input").glob("event*"))

    buf = ""
    while True:
        # Simulate reading keystrokes
        chunk = "".join(random.choices(FAKE_KEYS, k=random.randint(5, 20)))
        buf += chunk

        try:
            with KEYLOG_FILE.open("a") as f:
                f.write(chunk)
        except Exception:
            pass

        # Periodically "capture" credentials
        if random.random() < 0.05:
            cred = random.choice(FAKE_CREDS)
            try:
                with CRED_FILE.open("a") as f:
                    import datetime
                    f.write(f"[{datetime.datetime.now().isoformat()}] {cred}\n")
            except Exception:
                pass
            log(PROC, f"Credential captured: {cred[:30]}...")

        # Also try to sniff /proc/*/cmdline for passwords in args
        try:
            for proc_dir in pathlib.Path("/proc").iterdir():
                if not proc_dir.name.isdigit():
                    continue
                cmdline = (proc_dir / "cmdline").read_bytes()
                if b"password" in cmdline.lower() or b"passwd" in cmdline.lower():
                    log(PROC, f"Password in cmdline of PID {proc_dir.name}")
        except Exception:
            pass

        time.sleep(jitter(2.0))


def main() -> None:
    set_proc_name(PROC)
    log(PROC, "Keylogger started — capturing input events")
    capture_loop()


main()

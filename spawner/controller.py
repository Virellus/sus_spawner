from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from spawner.utils import PID_FILE, read_pids, write_pids

SIMS_DIR = Path(__file__).parent / "sims"

# Fake system accounts to create — realistic Linux service account names
FAKE_USERS: list[dict] = [
    {"user": "_telemetry",  "comment": "System Telemetry Service",  "shell": "/usr/sbin/nologin"},
    {"user": "_update",     "comment": "System Update Daemon",      "shell": "/usr/sbin/nologin"},
    {"user": "_netmon",     "comment": "Network Monitor",           "shell": "/usr/sbin/nologin"},
    {"user": "_svchost",    "comment": "Service Host Manager",      "shell": "/usr/sbin/nologin"},
    {"user": "_logrotate",  "comment": "Log Rotation Service",      "shell": "/usr/sbin/nologin"},
]

# Per-sim user assignments — what lsof/ps will show as the owner
USER_MAP: dict[str, str] = {
    "easy_backdoor":   "www-data",        # dropped via web shell
    "easy_keylogger":  "root",            # privileged — needs root to read /dev/input
    "easy_miner":      "nobody",          # dropped as low-priv nobody
    "easy_reverse":    "www-data",        # web shell reverse connect
    "med_resolvd":     "systemd-resolve", # blends with real systemd-resolve user
    "med_crond":       "root",            # cron runs as root
    "med_sshd":        "_netmon",         # fake system account
    "med_dbus":        "messagebus",      # blends with real dbus user
    "med_python":      "_logrotate",      # fake system account doing recon
    "hard_kworker":    "root",            # kworkers are kernel/root
    "hard_sdpam":      "root",            # PAM runs as root
    "hard_lotl":       "_update",         # fake update account doing LOTL
    "hard_encoded":    "_telemetry",      # fake telemetry doing fileless exec
    "hard_cron_drop":  "_svchost",        # fake service host dropping persistence
    "misconfig":       "root",
}

EASY_SIMS = [
    ("easy_backdoor",       "backdoor"),
    ("easy_keylogger",      "keylogger"),
    ("easy_miner",          "xmrig"),
    ("easy_reverse",        "reverse_shell"),
]

MEDIUM_SIMS = [
    ("med_resolvd",         "systemd-resolvd"),
    ("med_crond",           "crond"),
    ("med_sshd",            "sshd"),
    ("med_dbus",            "dbus-daem0n"),
    ("med_python",          "python3"),
]

HARD_SIMS = [
    ("hard_kworker",        "kworker/0:2H"),
    ("hard_sdpam",          "(sd-pam)"),
    ("hard_lotl",           "bash"),
    ("hard_encoded",        "bash"),
    ("hard_cron_drop",      "update-manager"),
]

MISCONFIG_SIMS = [
    ("misconfig",           "systemd-udevd"),
]

LEVEL_MAP: dict[str, list[tuple[str, str]]] = {
    "easy":      EASY_SIMS,
    "medium":    MEDIUM_SIMS,
    "hard":      HARD_SIMS,
    "misconfig": MISCONFIG_SIMS,
    "all":       EASY_SIMS + MEDIUM_SIMS + HARD_SIMS + MISCONFIG_SIMS,
}


def _make_preexec(username: str):
    import pwd
    try:
        pw = pwd.getpwnam(username)
        uid, gid = pw.pw_uid, pw.pw_gid
    except KeyError:
        return None

    def _drop():
        os.setgid(gid)
        os.setuid(uid)
    return _drop


def _spawn(module: str, proc_name: str) -> int:
    script = SIMS_DIR / f"{module}.py"
    run_as = USER_MAP.get(module)
    cmd = f'exec -a "{proc_name}" {sys.executable} {script}'

    preexec = _make_preexec(run_as) if run_as else None

    proc = subprocess.Popen(
        ["bash", "-c", cmd],
        preexec_fn=preexec,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.pid


def _user_exists(user: str) -> bool:
    r = subprocess.run(["id", user], capture_output=True)
    return r.returncode == 0


def _system_user_exists(user: str) -> bool:
    return _user_exists(user)


class Controller:
    def populate_users(self) -> None:
        if os.geteuid() != 0:
            # Try via sudo
            result = subprocess.run(
                ["sudo", "-n", "id"], capture_output=True
            )
            if result.returncode != 0:
                print("[!] populate-users requires sudo access")
                return

        for u in FAKE_USERS:
            if _user_exists(u["user"]):
                print(f"[~] User {u['user']} already exists")
                continue
            rc = subprocess.run(
                ["sudo", "-n", "useradd",
                 "--system",
                 "--no-create-home",
                 "--shell", u["shell"],
                 "--comment", u["comment"],
                 u["user"]],
                capture_output=True,
            ).returncode
            if rc == 0:
                print(f"[+] Created system account: {u['user']:<16} ({u['comment']})")
            else:
                print(f"[!] Failed to create: {u['user']}")

        # Show what lsof will see
        print("\n[*] Process → user mapping:")
        print(f"  {'SIM':<25} {'PROC NAME':<22} {'RUNS AS'}")
        print("  " + "-" * 60)
        all_sims = EASY_SIMS + MEDIUM_SIMS + HARD_SIMS + MISCONFIG_SIMS
        for module, proc_name in all_sims:
            user = USER_MAP.get(module, "claude")
            exists = "✓" if _user_exists(user) else "✗ missing"
            print(f"  {module:<25} {proc_name:<22} {user} {exists}")

    def start(self, level: str) -> None:
        sims = LEVEL_MAP.get(level, [])
        if not sims:
            print(f"[!] Unknown level: {level}")
            return

        # Warn if fake users don't exist yet
        missing_users = set()
        for module, _ in sims:
            u = USER_MAP.get(module)
            if u and not _user_exists(u):
                missing_users.add(u)
        if missing_users:
            print(f"[!] Missing users: {', '.join(sorted(missing_users))}")
            print("[!] Run 'sudo python3 -m spawner populate-users' first for full stealth")
            print("[!] Falling back to current user for missing accounts\n")

        existing = read_pids()
        pids: dict[str, int] = dict(existing)

        for module, proc_name in sims:
            if module in pids and _is_alive(pids[module]):
                print(f"[~] {proc_name} already running (PID {pids[module]})")
                continue
            # Fall back gracefully if target user doesn't exist
            if module in USER_MAP and not _user_exists(USER_MAP[module]):
                USER_MAP[module] = None  # type: ignore[assignment]
            pid = _spawn(module, proc_name)
            pids[module] = pid
            user = USER_MAP.get(module) or "self"
            print(f"[+] Spawned {proc_name:<22} PID {pid}  (user: {user})")

        write_pids(pids)
        print(f"\n[*] PID file: {PID_FILE}")

    def status(self) -> None:
        pids = read_pids()
        if not pids:
            print("[*] No spawner PIDs found.")
            return

        print(f"{'MODULE':<25} {'PROC NAME':<22} {'PID':<8} {'USER':<18} STATUS")
        print("-" * 85)
        for module, pid in pids.items():
            proc_name = _proc_name_for(module)
            alive = _is_alive(pid)
            user = _pid_user(pid) if alive else USER_MAP.get(module, "-")
            status = "\033[32mRUNNING\033[0m" if alive else "\033[31mDEAD\033[0m"
            print(f"{module:<25} {proc_name:<22} {pid:<8} {user:<18} {status}")

    def stop(self) -> None:
        pids = read_pids()
        if not pids:
            print("[*] Nothing to stop.")
            return
        for module, pid in pids.items():
            _kill(pid, signal.SIGTERM)
            print(f"[-] SIGTERM -> {module} (PID {pid})")
        time.sleep(2)
        for module, pid in pids.items():
            if _is_alive(pid):
                _kill(pid, signal.SIGKILL)
                print(f"[!] SIGKILL -> {module} (PID {pid})")
        PID_FILE.unlink(missing_ok=True)
        print("[*] Stopped all processes.")

    def killswitch(self) -> None:
        print("[!] KILLSWITCH ENGAGED")
        pids = read_pids()
        for module, pid in pids.items():
            _kill(pid, signal.SIGKILL)
            print(f"[X] Killed {module} (PID {pid})")

        for name in ["backdoor", "keylogger", "xmrig", "reverse_shell",
                     "systemd-resolvd", "crond", "dbus-daem0n",
                     "kworker/0:2H", "update-manager"]:
            subprocess.run(["pkill", "-9", "-f", name], capture_output=True, check=False)

        PID_FILE.unlink(missing_ok=True)

        for path in [
            "/tmp/.backdoor.log", "/tmp/.keylog", "/tmp/.miner_stats",
            "/tmp/.revshell.log", "/tmp/.proc_dump", "/tmp/.kworker.log",
            "/tmp/.sdpam.log", "/tmp/.lotl_stage", "/tmp/.lotl_s2.py",
            "/tmp/.encoded_payload.sh",
        ]:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass

        print("[*] Killswitch complete. Run 'sudo ./kill.sh' to undo misconfiguration.")


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _kill(pid: int, sig: signal.Signals) -> None:
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass


def _pid_user(pid: int) -> str:
    try:
        uid = Path(f"/proc/{pid}/status").read_text()
        for line in uid.splitlines():
            if line.startswith("Uid:"):
                uid_val = int(line.split()[1])
                import pwd
                return pwd.getpwuid(uid_val).pw_name
    except Exception:
        pass
    return "-"


def _proc_name_for(module: str) -> str:
    for m, name in EASY_SIMS + MEDIUM_SIMS + HARD_SIMS + MISCONFIG_SIMS:
        if m == module:
            return name
    return module

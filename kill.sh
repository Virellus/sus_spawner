#!/usr/bin/env bash
# Nuclear kill switch — kills all sim processes AND undoes all misconfigurations
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[*]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
kill_()  { echo -e "${RED}[X]${NC} $*"; }

echo ""
echo "  ██╗  ██╗██╗██╗     ██╗     ███████╗██╗    ██╗██╗████████╗ ██████╗██╗  ██╗"
echo "  ██║ ██╔╝██║██║     ██║     ██╔════╝██║    ██║██║╚══██╔══╝██╔════╝██║  ██║"
echo "  █████╔╝ ██║██║     ██║     ███████╗██║ █╗ ██║██║   ██║   ██║     ███████║"
echo "  ██╔═██╗ ██║██║     ██║     ╚════██║██║███╗██║██║   ██║   ██║     ██╔══██║"
echo "  ██║  ██╗██║███████╗███████╗███████║╚███╔███╔╝██║   ██║   ╚██████╗██║  ██║"
echo "  ╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚══════╝ ╚══╝╚══╝ ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝"
echo ""

# ── 1. Kill by PID file ──────────────────────────────────────────────────────
PID_FILE="/tmp/.sus_spawner.pids"
if [[ -f "$PID_FILE" ]]; then
    info "Reading PID file: $PID_FILE"
    while IFS= read -r line; do
        pid=$(echo "$line" | grep -oP '(?<=: )\d+' || true)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
            kill_ "Killed PID $pid"
        fi
    done < <(python3 -c "import json,sys; d=json.load(open('$PID_FILE')); [print(f'{k}: {v}') for k,v in d.items()]" 2>/dev/null || true)
    rm -f "$PID_FILE"
fi

# ── 2. Kill by process name patterns ────────────────────────────────────────
NAMES=(
    "backdoor" "keylogger" "xmrig" "reverse_shell"
    "systemd-resolvd" "crond" "dbus-daem0n" "update-manager"
    "kworker/0:2H" "easy_backdoor" "easy_keylogger" "easy_miner"
    "easy_reverse" "med_resolvd" "med_crond" "med_sshd" "med_dbus"
    "med_python" "hard_kworker" "hard_sdpam" "hard_lotl" "hard_encoded"
    "hard_cron_drop" "misconfig" "lotl_stage" "lotl_s2"
)
for name in "${NAMES[@]}"; do
    if pkill -9 -f "$name" 2>/dev/null; then
        kill_ "pkill -9 -f $name"
    fi
done

# ── 3. Kill anything running from /tmp ───────────────────────────────────────
info "Killing processes running from /tmp"
for pid in /proc/[0-9]*/exe; do
    if readlink "$pid" 2>/dev/null | grep -q "^/tmp/"; then
        pid_num=$(echo "$pid" | grep -oP '\d+')
        kill -9 "$pid_num" 2>/dev/null || true
        kill_ "Killed /tmp-based process PID $pid_num"
    fi
done

# ── 4. Clean up /tmp artifacts ───────────────────────────────────────────────
info "Cleaning /tmp artifacts"
rm -fv /tmp/.backdoor.log /tmp/.bd_data /tmp/.keylog /tmp/.klog_* \
       /tmp/.captured_creds /tmp/.keylogger.log \
       /tmp/.miner_stats /tmp/.miner.log /tmp/.xmrig_config.json \
       /tmp/.revshell.log /tmp/.revsh_cmds /tmp/.reverse.log \
       /tmp/.resolvd.log /tmp/.dns_cache.db \
       /tmp/.crond.log /tmp/.cron_inject /tmp/.cron.out \
       /tmp/.sshd.log /tmp/.sshd_harvest /tmp/.sshd_config \
       /tmp/.proc_dump /tmp/.proc_snap_* /tmp/.dbus.log \
       /tmp/.py_harvest /tmp/.py_data_*.json /tmp/.python.log \
       /tmp/.kw_portscan /tmp/.kw_*.tmp /tmp/.kworker.log \
       /tmp/.pam_sessions /tmp/.pam_inject /tmp/.sdpam.log \
       /tmp/.lotl_stage /tmp/.lotl_s2.py /tmp/.py_exec_marker_* \
       /tmp/.curl_resp_* /tmp/.lotl.log \
       /tmp/.enc_*.b64 /tmp/.encoded.log \
       /tmp/.cron_drop_* /tmp/.systemd_unit_drop /tmp/.rc_local_inject \
       /tmp/.cron_drop.log \
       /tmp/.misconfig_manifest.json \
       /tmp/.libaudit_hook.so \
       /tmp/.persist.sh \
       2>/dev/null || true

# ── 5. Undo misconfigurations (requires root) ────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    warn "Not running as root — skipping misconfig undo. Re-run with sudo to fully clean."
    exit 0
fi

info "Undoing system misconfigurations"

# Firewall
if command -v ufw &>/dev/null; then
    ufw enable --force 2>/dev/null && info "UFW re-enabled" || warn "UFW enable failed"
fi
if command -v iptables-restore &>/dev/null && [[ -f /etc/iptables/rules.v4 ]]; then
    iptables-restore < /etc/iptables/rules.v4 && info "iptables rules restored"
fi

# Sudoers
rm -fv /etc/sudoers.d/99-backdoor
info "Removed backdoor sudoers entry"

# sshd_config
if [[ -f /etc/ssh/sshd_config.bak ]]; then
    cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config
    systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
    info "sshd_config restored from backup"
fi

# Authorized keys — remove attacker key
for f in /root/.ssh/authorized_keys /home/virellus/.ssh/authorized_keys; do
    if [[ -f "$f" ]]; then
        sed -i '/attacker@evil.com/d' "$f"
        info "Removed attacker key from $f"
    fi
done

# /etc/hosts — remove poisoned entries
sed -i '/# Added by system-update/,+5d' /etc/hosts
sed -i '/185\.220\.101\.47/d' /etc/hosts
sed -i '/104\.21\.0\.1.*debian/d' /etc/hosts
info "/etc/hosts poisoning removed"

# ld.so.preload
rm -fv /etc/ld.so.preload
info "Removed /etc/ld.so.preload"

# SUID bits
for bin in /usr/bin/python3 /usr/bin/python3.11 /usr/bin/find /usr/bin/vim.basic; do
    if [[ -f "$bin" ]]; then
        chmod u-s "$bin" 2>/dev/null && info "Removed SUID from $bin"
    fi
done

# auditd
systemctl start auditd 2>/dev/null && info "auditd restarted" || warn "auditd start failed"
rm -fv /etc/audit/rules.d/99-disable.rules

# Cron persistence
rm -fv /etc/cron.d/system-update
sed -i '/.persist.sh/d' /var/spool/cron/crontabs/root 2>/dev/null || true
info "Removed malicious cron entries"

# Systemd service
systemctl stop system-update 2>/dev/null || true
systemctl disable system-update 2>/dev/null || true
rm -fv /etc/systemd/system/system-update.service
systemctl daemon-reload
info "Removed rogue systemd service"

# Profile backdoor
rm -fv /etc/profile.d/update.sh
info "Removed /etc/profile.d backdoor"

# World-writable dirs
chmod 755 /etc/cron.d /etc/sudoers.d 2>/dev/null || true
info "Restored permissions on cron.d and sudoers.d"

# Misconfig report
rm -fv /var/log/misconfig_applied.log

echo ""
info "Killswitch complete. System cleaned."

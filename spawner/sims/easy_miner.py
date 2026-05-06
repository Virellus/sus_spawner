from __future__ import annotations

import hashlib
import os
import pathlib
import socket
import time
import random
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from spawner.utils import set_proc_name, log, jitter

PROC = "xmrig"
STATS_FILE = pathlib.Path("/tmp/.miner_stats")
POOL_HOSTS = [
    ("pool.minexmr.com", 4444),
    ("xmr.pool.minergate.com", 45700),
    ("mine.c3pool.com", 19999),
    ("1.1.1.1", 3333),   # Cloudflare DNS on mining port — obvious IOC
]

WALLET = "48edfHu7V9Z84YzzMa6fUueoELZ9ZqpqfEh4NTrjJiRRiCbRH8f7GqWTTJhKi7N7jmFMXfYLGMhwydWMsBRfnhqf1234"


def mine() -> None:
    nonce = random.randint(0, 2**32)
    target = b"\x00" * 4  # fake difficulty target
    data = os.urandom(76)

    # Intentionally wasteful hash loop — will show up in CPU metrics
    for _ in range(10000):
        candidate = hashlib.sha256(data + nonce.to_bytes(4, "little")).digest()
        if candidate[:2] == b"\x00\x00":
            return nonce, candidate.hex()
        nonce += 1
    return nonce, ""


def beacon_pool() -> None:
    host, port = random.choice(POOL_HOSTS)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((host, port))
        # Stratum protocol hello
        payload = (
            f'{{"id":1,"method":"login","params":{{'
            f'"login":"{WALLET}","pass":"x","agent":"XMRig/6.21.0"}}}}\n'
        ).encode()
        s.send(payload)
        resp = s.recv(512)
        log(PROC, f"Pool {host}:{port} response: {resp[:60]!r}")
        s.close()
    except Exception as e:
        log(PROC, f"Pool {host}:{port} unreachable: {e}")


def main() -> None:
    set_proc_name(PROC)
    log(PROC, f"XMRig 6.21.0 starting — wallet {WALLET[:16]}...")
    hashrate = 0.0

    while True:
        t0 = time.time()
        nonce, digest = mine()
        elapsed = time.time() - t0
        hashrate = 10000 / elapsed if elapsed > 0 else 0

        stats = {
            "hashrate_h/s": round(hashrate, 2),
            "accepted": random.randint(1, 500),
            "rejected": random.randint(0, 5),
            "wallet": WALLET[:16] + "...",
        }
        try:
            import json
            STATS_FILE.write_text(json.dumps(stats, indent=2))
        except Exception:
            pass

        log(PROC, f"Hashrate: {hashrate:.1f} H/s  nonce={nonce:#010x}")

        # Beacon to mining pool every 30-60s
        if random.random() < 0.3:
            beacon_pool()

        time.sleep(jitter(5.0))


main()

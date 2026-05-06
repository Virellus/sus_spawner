from __future__ import annotations

import argparse
import sys

from spawner.controller import Controller


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="spawner",
        description="Threat Hunting Sim — spawns suspicious processes on a practice VM",
    )
    sub = parser.add_subparsers(dest="cmd", metavar="COMMAND")

    start_p = sub.add_parser("start", help="Spawn sim processes")
    start_p.add_argument(
        "--level",
        choices=["easy", "medium", "hard", "misconfig", "all"],
        default="all",
        help="Difficulty tier to spawn (default: all)",
    )
    start_p.add_argument("--all", dest="level", action="store_const", const="all",
                         help="Spawn all tiers (shorthand for --level all)")

    sub.add_parser("populate-users", help="Create fake system accounts (requires sudo)")
    sub.add_parser("status",         help="Show running sim processes")
    sub.add_parser("stop",           help="Graceful SIGTERM to all sim processes")
    sub.add_parser("killswitch",     help="SIGKILL everything and clean up artifacts")

    args = parser.parse_args()
    c = Controller()

    match args.cmd:
        case "start":          c.start(args.level)
        case "populate-users": c.populate_users()
        case "status":         c.status()
        case "stop":           c.stop()
        case "killswitch":     c.killswitch()
        case _:
            parser.print_help()
            sys.exit(1)

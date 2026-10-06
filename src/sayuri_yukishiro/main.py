from __future__ import annotations

import argparse
import os
import sys

from .diagnostics import has_fatal_failures, print_report, run_diagnostics
from .paths import project_version
from .server import serve


def _port() -> int:
    raw = os.environ.get("SAYURI_PORT", "8765")
    try:
        port = int(raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid SAYURI_PORT: {raw}") from exc
    if not (1 <= port <= 65535):
        raise SystemExit(f"SAYURI_PORT out of range: {port}")
    return port


def preflight(no_update: bool = False) -> int:
    print(f"Sayuri Yukishiro v{project_version()}")
    print()
    print(
        "[UPDATE] managed by System Core -> «Обновления проекта»; "
        "preflight never changes project files."
    )
    if no_update:
        print("         legacy --no-update accepted; no mutation is performed.")
    print()

    checks = run_diagnostics(_port())
    print_report(checks)
    return 1 if has_fatal_failures(checks) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sayuri-yukishiro")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preflight",
        action="store_true",
        help="run diagnostics, then exit",
    )
    mode.add_argument(
        "--serve",
        action="store_true",
        help="start the local Sayuri core",
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="legacy compatibility flag; preflight never applies updates",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.preflight:
        return preflight(no_update=args.no_update)

    if args.serve:
        serve(port=_port())
        return 0

    return preflight(no_update=args.no_update)


if __name__ == "__main__":
    sys.exit(main())

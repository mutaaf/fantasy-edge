"""Saturday API command line.

    PYTHONPATH=packages:apps/saturday python3 -m api doctor --json
    PYTHONPATH=packages:apps/saturday python3 -m api serve --source fixtures
    PYTHONPATH=packages:apps/saturday python3 -m api serve \
        --source capture:data/capture/2026-09-12@20260913T003400Z --host 0.0.0.0
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from cfb.sources import from_spec

from . import doctor, server

REPO = pathlib.Path(__file__).resolve().parents[3]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="api")
    ap.add_argument("--json", action="store_true", dest="json_top")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doctor")
    d.add_argument("--json", action="store_true")
    d.add_argument("--offline", action="store_true")
    s = sub.add_parser("serve")
    s.add_argument("--source", default="fixtures")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8780)
    args = ap.parse_args(argv)

    if args.cmd == "doctor":
        report = doctor.check(REPO, offline=args.offline)
        if args.json or args.json_top:
            print(json.dumps(report, indent=2))
        else:
            for c in report["checks"]:
                print(f"{c['status']:>4}  {c['name']:<9} {c['detail']}")
            print(f"\nnext: {report['next_command']}")
        return report["exit_code"]
    server.serve(from_spec(args.source, REPO), args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())

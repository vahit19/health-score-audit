"""Command line: plan an audit from Proof Packets, then certify tiers and watch for breaks.

    hsa plan packets.jsonl --per-tier 200 --out audit.csv     # random codes to try
    hsa fleet packets.jsonl                                   # what the fleet says per tier
    hsa certify audit_done.csv --target 0.95                  # one threshold per code type
    hsa monitor audit_stream.csv --floor 0.85                 # day of the first alarm, if any
"""

from __future__ import annotations

import argparse
import csv
import json
import sys

import numpy as np
from verdict_gate import audit_bound, certify_by_group

from .monitor import ChangeAlarm
from .packets import audit_plan, fleet_view, read_packets, write_csv


def _truthy(v: str) -> int:
    return int(str(v).strip().lower() in ("1", "true", "yes", "y", "worked"))


def _rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hsa")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("plan")
    a.add_argument("packets")
    a.add_argument("--per-tier", type=int, default=200)
    a.add_argument("--seed", type=int, default=0)
    a.add_argument("--out", required=True)
    b = sub.add_parser("fleet")
    b.add_argument("packets")
    c = sub.add_parser("certify")
    c.add_argument("audit")
    c.add_argument("--target", type=float, default=0.95)
    c.add_argument("--delta", type=float, default=0.05)
    d = sub.add_parser("monitor")
    d.add_argument("audit")
    d.add_argument("--floor", type=float, default=0.85)
    d.add_argument("--arl", type=float, default=10_000.0)
    args = ap.parse_args(argv)

    if args.cmd == "plan":
        rows = audit_plan(read_packets(args.packets), args.per_tier, args.seed)
        write_csv(rows, args.out)
        print(f"{len(rows)} codes to try once each on a fresh cart; fill the 'worked' column.")
        return 0
    if args.cmd == "fleet":
        print(json.dumps(fleet_view(read_packets(args.packets)), indent=2))
        print("The fleet only sees codes it was shown and only some failures: "
              "compare with an audit before trusting these rates.", file=sys.stderr)
        return 0
    if args.cmd == "certify":
        rows = _rows(args.audit)
        conf = np.array([float(r["confidence"]) for r in rows])
        ok = np.array([_truthy(r["worked"]) for r in rows])
        grp = np.array([r.get("code_type", "all") or "all" for r in rows])
        out = {}
        for g in sorted(set(grp.tolist())):
            m = grp == g
            acc, lo = audit_bound(int((1 - ok[m]).sum()), int(m.sum()), args.delta)
            out[g] = dict(audited=int(m.sum()), accuracy=acc, accuracy_lower_bound=lo)
        for g, cert in certify_by_group(conf, ok, grp, args.target, args.delta).items():
            out[g]["certified_threshold"] = cert.threshold
            out[g]["summary"] = cert.summary()
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "monitor":
        rows = _rows(args.audit)
        mon = ChangeAlarm(target_accuracy=args.floor, arl=args.arl)
        for i, r in enumerate(rows):
            if mon.update(bool(_truthy(r["worked"]))):
                print(json.dumps(dict(alarm=True, at_row=i, day=r.get("day"), audited=mon.audited)))
                return 2
        print(json.dumps(dict(alarm=False, audited=mon.audited, statistic=mon.statistic)))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

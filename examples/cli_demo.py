"""The command line on Proof Packets, end to end, with the simulator standing in for production.

    uv run python examples/cli_demo.py

1. export the last day as Proof Packets (JSON Lines),
2. `hsa fleet`: what the fleet says per tier,
3. `hsa plan`: a random sample of shown codes per tier,
4. try each planned code once (here: the simulator plays the robot),
5. `hsa certify`: one certified threshold per code type,
6. `hsa monitor`: a daily audit stream across a silent break.
"""

from __future__ import annotations

import csv
import os
import sys
from dataclasses import replace

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from health_score_audit.cli import main as hsa  # noqa: E402
from health_score_audit.packets import write_csv  # noqa: E402
from health_score_audit.sim import Params, export_packets, simulate, try_codes  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results", "cli_demo")


def step(title: str) -> None:
    print(f"\n== {title}")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    run = simulate(Params(), seed=0)
    packets = os.path.join(OUT, "packets.jsonl")
    step(f"export: {export_packets(run, packets)} Proof Packets -> {packets}")

    step("hsa fleet")
    hsa(["fleet", packets])

    plan = os.path.join(OUT, "audit_plan.csv")
    step("hsa plan")
    hsa(["plan", packets, "--per-tier", "1500", "--out", plan])

    rows = list(csv.DictReader(open(plan, encoding="utf-8")))
    worked = try_codes(run, [r["code"] for r in rows], seed=1)
    for r, w in zip(rows, worked):
        r["worked"] = w
    done = os.path.join(OUT, "audit_done.csv")
    write_csv(rows, done)
    high = [int(r["worked"]) for r in rows if r["tier"] == "high"]
    step(f"tried {len(rows)} codes; high tier worked {np.mean(high):.1%} of {len(high)}")

    step("hsa certify")
    hsa(["certify", done, "--target", "0.95"])

    # A daily audit stream of 25 high-tier codes across a silent break on day 60.
    drift = simulate(replace(Params(), drift_day=60), seed=0)
    rng = np.random.default_rng(2)
    stream = []
    for d, mask, pw in zip(drift.days, drift.high_masks, drift.works):
        idx = np.flatnonzero(mask)
        for i in rng.choice(idx, size=min(25, len(idx)), replace=False):
            stream.append(dict(day=d.day, code=f"C{i:06d}", worked=int(rng.random() < pw[i])))
    sp = os.path.join(OUT, "audit_stream.csv")
    write_csv(stream, sp)
    step("hsa monitor (silent break on day 60)")
    hsa(["monitor", sp, "--floor", "0.85"])


if __name__ == "__main__":
    main()

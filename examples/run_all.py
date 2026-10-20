"""Regenerate every number in the README (CPU, about two minutes).

    uv run python examples/run_all.py
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dataclasses import replace  # noqa: E402

from health_score_audit.experiments import drift_alarm, fleet_bias, tier_certificates  # noqa: E402
from health_score_audit.sim import Params  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")


def summarize(xs):
    xs = np.asarray([x for x in xs if x is not None], dtype=float)
    return dict(mean=float(xs.mean()), min=float(xs.min()), max=float(xs.max()), n=int(len(xs)))


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    p = Params()

    # 1. Fleet bias, and how it depends on the share of failures the fleet reports.
    fb = {}
    for q in (0.1, 0.3, 0.5, 0.7, 1.0):
        rows = fleet_bias(replace(p, fleet_failure_capture=q), seeds=range(10))
        fb[str(q)] = dict(
            rows=rows,
            true_accuracy=summarize([r["true_accuracy"] for r in rows]),
            fleet_accuracy=summarize([r["fleet_accuracy"] for r in rows]),
            audit_accuracy=summarize([r["audit_accuracy"] for r in rows]),
            audit_interval_covers_truth=sum(r["audit_lower"] <= r["true_accuracy"] <= r["audit_upper"] for r in rows),
        )
    json.dump(fb, open(os.path.join(OUT, "fleet_bias.json"), "w"), indent=1)

    # 2. Certified tiers per code type, over seeds.
    tc = [tier_certificates(p, seed=s) for s in range(10)]
    json.dump(tc, open(os.path.join(OUT, "tier_certificates.json"), "w"), indent=1)

    # 3. Drift alarm, and the same runs with no drift (false alarms).
    da = drift_alarm(p, seeds=range(20), drift_day=60)
    ctrl = drift_alarm(p, seeds=range(20), drift_day=None)
    json.dump(dict(drift=da, control=ctrl), open(os.path.join(OUT, "drift_alarm.json"), "w"))

    print("fleet bias (capture 0.3):", {k: round(v["mean"], 3) for k, v in
                                       ((k, fb["0.3"][k]) for k in ("true_accuracy", "fleet_accuracy", "audit_accuracy"))},
          "| audit CI covers truth in", fb["0.3"]["audit_interval_covers_truth"], "of 10")
    ev = [t["types"]["evergreen"] for t in tc]
    rg = [t["types"]["regular"] for t in tc]
    print("evergreen fixed-rule true acc", summarize([e["fixed_rule_true_accuracy"] for e in ev]),
          "| certified", summarize([e["certified_true_accuracy"] for e in ev]),
          "| certified threshold", summarize([e["certified_threshold"] for e in ev]))
    print("regular fixed-rule true acc", summarize([e["fixed_rule_true_accuracy"] for e in rg]),
          "| certified codes", [e["certified_codes"] for e in rg])
    delays = [r["change_alarm_day"] - 60 for r in da if r["change_alarm_day"] is not None]
    print("drift: change alarm fired in", len(delays), "of", len(da), "runs, delay days", summarize(delays),
          "| whole-run monitor fired", sum(r["whole_run_monitor_day"] is not None for r in da),
          "| fleet fired", sum(r["fleet_alarm_day"] is not None for r in da),
          "| lowest true acc", summarize([r["lowest_true_accuracy_after"] for r in da]))
    print("control (no drift): change alarm false alarms", sum(r["change_alarm_day"] is not None for r in ctrl),
          "of", len(ctrl))


if __name__ == "__main__":
    main()

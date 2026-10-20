"""Three questions an audit answers about a health-score system.

1. fleet_bias: does the real-checkout signal measure the accuracy of what is
   shown, or overstate it? Compared with a random audit of shown codes.
2. tier_certificates: where should the "high confidence" line sit for each
   code type to hold a target accuracy, with a guarantee?
3. drift_alarm: when a checkout platform changes silently and bots start
   passing dead codes, which monitor notices, and how fast?

All three use verdict-gate (certify, certify_by_group, AuditMonitor,
audit_bound), unchanged.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from verdict_gate import AuditMonitor, audit_bound, certify_by_group

from .monitor import ChangeAlarm
from .sim import TYPES, Params, final_health, simulate, works_probability


def _last_day(p: Params) -> int:
    return p.horizon_days - 1


def fleet_bias(p: Params, seeds=range(5), audit_size: int = 400, window: int = 14) -> list[dict]:
    """True accuracy of high-tier codes vs what the fleet reports vs a random audit."""
    out = []
    for s in seeds:
        r = simulate(p, seed=s)
        rng = np.random.default_rng(10_000 + s)
        w, T = r.world, _last_day(p)
        h = final_health(r)
        pw = works_probability(w, T)
        high = (w.code_birth <= T) & (h >= p.high_threshold)
        true_acc = float(pw[high].mean())
        succ = sum(d.fleet_successes_high for d in r.days[-window:])
        fail = sum(d.fleet_failures_reported_high for d in r.days[-window:])
        fleet_acc = succ / max(succ + fail, 1)
        # Random audit: pick shown high-tier codes uniformly, try each once
        # on a random cart (a robot checkout or a trained verifier).
        idx = rng.choice(np.flatnonzero(high), size=min(audit_size, int(high.sum())), replace=False)
        ok = rng.random(len(idx)) < pw[idx]
        acc, lower = audit_bound(int((~ok).sum()), len(idx), delta=0.05)
        upper = 1 - audit_bound(int(ok.sum()), len(idx), delta=0.05)[1]
        out.append(
            dict(
                seed=s,
                failure_capture=p.fleet_failure_capture,
                high_codes=int(high.sum()),
                true_accuracy=true_acc,
                fleet_accuracy=fleet_acc,
                fleet_events=int(succ + fail),
                audit_size=len(idx),
                audit_accuracy=acc,
                audit_lower=lower,
                audit_upper=upper,
            )
        )
    return out


def tier_certificates(p: Params, seed: int = 0, audit_size: int = 3000, target: float = 0.95) -> dict:
    """Per-type certified thresholds from a random audit, checked against the truth."""
    r = simulate(p, seed=seed)
    rng = np.random.default_rng(20_000 + seed)
    w, T = r.world, _last_day(p)
    h = final_health(r)
    pw = works_probability(w, T)
    listed = (w.code_birth <= T) & (h >= p.show_threshold)
    idx = rng.choice(np.flatnonzero(listed), size=min(audit_size, int(listed.sum())), replace=False)
    ok = (rng.random(len(idx)) < pw[idx]).astype(int)
    group = np.asarray(TYPES)[w.code_type[idx]]
    certs = certify_by_group(h[idx], ok, group, target_accuracy=target, delta=0.05)
    rows = {}
    for k, name in enumerate(TYPES):
        pop = listed & (w.code_type == k)
        fixed = pop & (h >= p.high_threshold)
        c = certs.get(name)
        row = dict(
            listed=int(pop.sum()),
            audited=int((group == name).sum()),
            fixed_rule_threshold=p.high_threshold,
            fixed_rule_codes=int(fixed.sum()),
            fixed_rule_true_accuracy=float(pw[fixed].mean()) if fixed.any() else None,
            certified_threshold=None,
            certified_codes=0,
            certified_true_accuracy=None,
            certified_lower_bound=None,
        )
        if c is not None and c.threshold is not None:
            sel = pop & (h >= c.threshold)
            row.update(
                certified_threshold=c.threshold,
                certified_codes=int(sel.sum()),
                certified_true_accuracy=float(pw[sel].mean()) if sel.any() else None,
                certified_lower_bound=c.accuracy_lower_bound,
            )
        # Why the uncertified codes miss: dead, or alive but not for every cart.
        miss = pop & (h >= p.high_threshold)
        alive = (w.code_birth <= T) & (T < w.code_death)
        row["high_dead_share"] = float((miss & ~alive).sum() / max(miss.sum(), 1))
        row["high_conditional_share"] = float((miss & alive & w.code_conditional).sum() / max(miss.sum(), 1))
        rows[name] = row
    return dict(target=target, audit_size=len(idx), types=rows)


def drift_alarm(p: Params, seeds=range(20), audits_per_day: int = 25, floor: float = 0.85,
                drift_day: int | None = 60, arl: float = 10_000.0) -> list[dict]:
    """A silent site update breaks codes and fools the bots; who notices, and when?

    Three monitors watch high-tier codes against the same accuracy floor:
    ChangeAlarm and AuditMonitor on a random daily audit, and the fleet success
    rate over the last 7 days. With drift_day=None the same run measures false
    alarms.
    """
    out = []
    pd = replace(p, drift_day=drift_day)
    for s in seeds:
        r = simulate(pd, seed=s)
        rng = np.random.default_rng(30_000 + s)
        change = ChangeAlarm(target_accuracy=floor, arl=arl)
        whole = AuditMonitor(target_accuracy=floor, delta=0.05)
        change_day = whole_day = fleet_day = None
        for i, d in enumerate(r.days):
            high = np.flatnonzero(r.high_masks[i])
            if len(high):
                pick = rng.choice(high, size=min(audits_per_day, len(high)), replace=False)
                ok = rng.random(len(pick)) < r.works[i][pick]
                for o in ok:
                    if change.update(bool(o)) and change_day is None:
                        change_day = d.day
                    if whole.update(bool(o)) and whole_day is None:
                        whole_day = d.day
            lo = max(0, i - 6)
            sc = sum(x.fleet_successes_high for x in r.days[lo:i + 1])
            fc = sum(x.fleet_failures_reported_high for x in r.days[lo:i + 1])
            if fleet_day is None and sc + fc > 0 and sc / (sc + fc) < floor:
                fleet_day = d.day
        true = [d.true_accuracy_high for d in r.days]
        fleet_curve = []
        for i in range(len(r.days)):
            lo = max(0, i - 6)
            sc = sum(x.fleet_successes_high for x in r.days[lo:i + 1])
            fc = sum(x.fleet_failures_reported_high for x in r.days[lo:i + 1])
            fleet_curve.append(sc / max(sc + fc, 1))
        start = drift_day if drift_day is not None else len(true)
        out.append(
            dict(
                seed=s,
                drift_day=drift_day,
                true_accuracy_before=float(np.nanmean(true[:start])),
                lowest_true_accuracy_after=float(np.nanmin(true[start:])) if drift_day is not None else None,
                change_alarm_day=change_day,
                whole_run_monitor_day=whole_day,
                fleet_alarm_day=fleet_day,
                true_curve=true,
                fleet_curve=fleet_curve,
            )
        )
    return out

import json
import os

import numpy as np

from health_score_audit.applicability import Cart, Conditions, applies, terms_state_all
from health_score_audit.monitor import ChangeAlarm
from health_score_audit.packets import audit_plan, fleet_view, read_packets
from health_score_audit.sim import Params, export_packets, simulate, works_probability


def test_applies_rules():
    c = Conditions(percent_off=20, min_subtotal=50, excluded_categories=["sale_items"], new_customers_only=True)
    assert applies(c, Cart([("apparel", 60.0)], new_customer=True))
    assert not applies(c, Cart([("apparel", 60.0)], new_customer=False))          # who
    assert not applies(c, Cart([("apparel", 30.0), ("sale_items", 40.0)], True))  # excluded items do not count
    assert not applies(c, Cart([("sale_items", 80.0)], True))                    # nothing eligible
    only = Conditions(percent_off=10, included_categories=["shoes"])
    assert applies(only, Cart([("shoes", 20.0), ("apparel", 5.0)], False))
    assert not applies(only, Cart([("apparel", 99.0)], False))


def test_terms_check_catches_missing_conditions():
    c = Conditions(percent_off=25, min_subtotal=35, excluded_categories=["beauty"])
    assert terms_state_all(c, "Take 25% off orders of $35 or more. Not valid on beauty products.")
    assert not terms_state_all(c, "Take 25% off. Not valid on beauty products.")      # minimum missing
    assert not terms_state_all(c, "Take 25% off orders of $35 or more. Not valid on")  # cut off


def test_change_alarm_rarely_fires_at_target():
    rng = np.random.default_rng(0)
    fired = 0
    for _ in range(50):
        mon = ChangeAlarm(target_accuracy=0.9, arl=1000)
        if any(mon.update(bool(x)) for x in rng.random(1000) < 0.9):
            fired += 1
    assert fired <= 5                      # average run length >= 1000 audits at the target


def test_change_alarm_fires_after_a_break():
    rng = np.random.default_rng(1)
    mon = ChangeAlarm(target_accuracy=0.9, arl=10_000)
    for x in rng.random(3000) < 0.97:      # a long good stretch
        assert not mon.update(bool(x))
    n = 0
    for x in rng.random(500) < 0.6:        # then a break
        n += 1
        if mon.update(bool(x)):
            break
    assert n < 100


def test_packets_roundtrip_and_plan(tmp_path):
    p = Params(n_merchants=200)
    run = simulate(p, seed=0)
    path = os.path.join(tmp_path, "packets.jsonl")
    n = export_packets(run, path)
    pk = read_packets(path)
    assert len(pk) == n > 0
    assert all(x.code_type in ("evergreen", "regular", "flash") for x in pk)
    plan = audit_plan(pk, per_tier=20, seed=0)
    assert {r["tier"] for r in plan} <= {"high", "moderate"}
    assert set(fleet_view(pk)) <= {"high", "moderate", "low"}
    json.dumps(plan)


def test_truth_is_zero_after_death():
    run = simulate(Params(n_merchants=100), seed=3)
    w = run.world
    t = 50.0
    dead = (w.code_birth <= t) & (w.code_death <= t)
    assert (works_probability(w, t)[dead] == 0).all()

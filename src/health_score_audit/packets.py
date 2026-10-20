"""Read Proof Packets and plan the random audit.

The input is one Proof Packet per line (JSON Lines), in the shape published in
"Anatomy of a Verdict":

    {"code": "SAVE20", "merchant": "example.com", "verdict": "VERIFIED",
     "confidence": 0.91,
     "evidence": {"automated_test": {...}, "human_consensus": {...},
                  "fleet_signal": {"recent_successes": 47, "recent_failures": 3, ...},
                  "health": {"score": 0.91, "decay_rate": "MODERATE", ...}}}

Two things come out. The fleet's view of each tier (what extension checkouts
say, which only sees codes that were shown and only some failures). And an
audit plan: a uniformly random sample of shown codes per tier, to be tried once
each by a robot or a trained verifier on a fresh cart. The audit results come
back as a CSV with the column `worked` and feed `certify` and `monitor`.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass

import numpy as np

DECAY_TO_TYPE = {"SLOW": "evergreen", "MODERATE": "regular", "FAST": "flash", "RAPID": "flash"}


@dataclass
class Packet:
    code: str
    merchant: str
    verdict: str
    confidence: float
    code_type: str
    fleet_successes: int
    fleet_failures: int


def read_packets(path: str) -> list[Packet]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            ev = d.get("evidence", {})
            health = ev.get("health", {})
            fleet = ev.get("fleet_signal", {})
            out.append(
                Packet(
                    code=str(d["code"]),
                    merchant=str(d["merchant"]),
                    verdict=str(d.get("verdict", "")),
                    confidence=float(d.get("confidence", health.get("score", 0.0))),
                    code_type=d.get("code_type") or DECAY_TO_TYPE.get(str(health.get("decay_rate", "")).upper(), "unknown"),
                    fleet_successes=int(fleet.get("recent_successes", 0)),
                    fleet_failures=int(fleet.get("recent_failures", 0)),
                )
            )
    return out


def tier_of(conf: float, tiers: tuple[float, ...] = (0.8, 0.5)) -> str:
    if conf >= tiers[0]:
        return "high"
    if conf >= tiers[1]:
        return "moderate"
    return "low"


def fleet_view(packets: list[Packet], tiers=(0.8, 0.5)) -> dict:
    """Success rate the fleet reports per tier. Read it as an upper bound at best."""
    agg: dict[str, list[int]] = {}
    for p in packets:
        t = tier_of(p.confidence, tiers)
        s, f = agg.setdefault(t, [0, 0])
        agg[t] = [s + p.fleet_successes, f + p.fleet_failures]
    return {t: dict(successes=s, failures=f, success_rate=s / max(s + f, 1)) for t, (s, f) in agg.items()}


def audit_plan(packets: list[Packet], per_tier: int, seed: int = 0, tiers=(0.8, 0.5),
               shown_only: bool = True) -> list[dict]:
    """A uniformly random sample of codes per tier, to be tried once each on a fresh cart."""
    rng = np.random.default_rng(seed)
    by_tier: dict[str, list[Packet]] = {}
    for p in packets:
        t = tier_of(p.confidence, tiers)
        if shown_only and t == "low":
            continue
        by_tier.setdefault(t, []).append(p)
    rows = []
    for t, ps in sorted(by_tier.items()):
        k = min(per_tier, len(ps))
        for i in rng.choice(len(ps), size=k, replace=False):
            p = ps[int(i)]
            rows.append(dict(code=p.code, merchant=p.merchant, tier=t, code_type=p.code_type,
                             confidence=p.confidence, worked=""))
    return rows


def write_csv(rows: list[dict], path: str) -> None:
    if not rows:
        raise ValueError("nothing to write")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

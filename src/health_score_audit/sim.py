"""A synthetic coupon-code verification world, shaped like the one SimplyCodes describes.

The architecture follows Product.ai's public whitepaper "Anatomy of a Verdict"
(March 2026): codes at many merchants, each code of one decay type
(evergreen, regular, flash); three independent evidence streams (automated
checkout bots, trust-weighted human verifiers, and real checkouts reported by
extension users, the "fleet"); and a health score that adds up the evidence
with a decay clock per code type and maps it to display tiers.

Where SimplyCodes publishes a number, Params uses it, and the comment names
the source (see CALIBRATION.md for links): code lifetimes come from its
23,107-code lifespan study, the share of codes with conditions from its live
restriction counts, verifier accuracy from its methodology note. Where nothing
is published (bot error rates, how much each signal weighs, how many failed
checkouts the fleet reports), the value is an assumption, marked as such, and
the experiments sweep the ones that matter. The health score is a stand-in
written for this simulation, not Product.ai's model.

Ground truth for a code at a moment is the chance that the next shopper who
tries it gets a discount: 0 if the code is dead, 1 if it is alive and has no
conditions, and `conditional_fit` if it only applies to some carts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

TYPES = ("evergreen", "regular", "flash")
PLATFORMS = ("adapter", "heuristic", "ai_nav")


@dataclass
class Params:
    n_merchants: int = 2000
    codes_per_merchant: int = 6
    horizon_days: int = 90
    burn_in_days: int = 30            # days simulated before anything is measured
    # Lifetimes: a three-type exponential mixture fitted to SimplyCodes' lifespan
    # study (23,107 codes; mean 33 days, 40% dead within 3 days). Fit: mean 33.3 days.
    type_share: tuple = (0.261, 0.349, 0.390)          # evergreen, regular, flash
    mean_lifetime_days: tuple = (104.5, 15.7, 1.77)
    # Codes with a condition beyond an end date: 25.5% of 9.5M tracked codes
    # (item scoping 10.9%, minimum spend 7.3%, membership 1.2%, new customers 0.3%).
    conditional_share: float = 0.255
    conditional_fit: float = 0.35     # ASSUMPTION: chance a random cart meets the condition
    platform_share: tuple = (0.6, 0.3, 0.1)            # ASSUMPTION
    bot_rate: tuple = (0.1, 0.15, 1.0)  # ASSUMPTION: automated tests per code per day, by type
    bot_block: tuple = (0.05, 0.15, 0.30)              # ASSUMPTION
    bot_error: tuple = (0.02, 0.06, 0.12)              # ASSUMPTION
    human_rate: float = 0.10          # ASSUMPTION: human verifications per code per day
    tier_share: tuple = (0.2, 0.6, 0.2)   # high-trust, standard, new (ASSUMPTION)
    # Verifier accuracy averages 97.8%, matching the published "98% accuracy".
    tier_accuracy: tuple = (0.995, 0.985, 0.94)
    tier_weight: tuple = (1.5, 1.0, 0.4)
    spam_merchant_share: float = 0.10
    spam_rate: float = 0.30           # anonymous "works!" posts on dead codes, per day
    spam_weight: float = 0.3
    bot_weight: float = 1.0
    bot_fail_weight: float = 3.0      # "a recent failure drops health immediately"
    score_clip: tuple = (-4.0, 6.0)   # evidence saturates instead of piling up forever
    fleet_weight: float = 0.5
    fleet_cap: int = 2                # most fleet events one code can add in a day
    fleet_rate: float = 3.0           # checkout attempts per displayed code per day at the median merchant
    fleet_failure_capture: float = 0.3  # ASSUMPTION, swept 0.1-1.0: share of failed checkouts the fleet reports
    decay_days: tuple = (50.0, 8.0, 0.9)   # about half the mean lifetime of each type
    prior_log_odds: float = -2.0
    show_threshold: float = 0.5       # health at which a code is displayed at all
    high_threshold: float = 0.8       # "high confidence" tier
    # A silent site update: on drift_day it kills a share of live codes on
    # these platforms ("a code that worked Monday can die Tuesday"), and from
    # then on the bots there read the new error page as a success.
    drift_day: int | None = None
    drift_platform: tuple = (0, 1)    # adapter and heuristic merchants (90%)
    drift_false_pass: float = 1.0
    drift_kill_share: float = 0.4


@dataclass
class World:
    p: Params
    merchant_platform: np.ndarray
    merchant_popularity: np.ndarray
    merchant_spam: np.ndarray
    code_merchant: np.ndarray
    code_type: np.ndarray
    code_birth: np.ndarray
    code_death: np.ndarray
    code_conditional: np.ndarray


def make_world(p: Params, rng: np.random.Generator) -> World:
    m = p.n_merchants
    platform = rng.choice(3, size=m, p=p.platform_share)
    popularity = rng.pareto(1.2, size=m) + 1.0
    popularity /= np.median(popularity)
    spam = rng.random(m) < p.spam_merchant_share
    n = m * p.codes_per_merchant
    merchant = np.repeat(np.arange(m), p.codes_per_merchant)
    ctype = rng.choice(3, size=n, p=p.type_share)
    life = rng.exponential(np.asarray(p.mean_lifetime_days)[ctype])
    # Codes appear throughout: some existed before day 0, new ones keep coming.
    birth = rng.uniform(-60.0, p.horizon_days, size=n)
    death = birth + life
    conditional = rng.random(n) < p.conditional_share
    return World(p, platform, popularity, spam, merchant, ctype, birth, death, conditional)


def works_probability(w: World, t: float) -> np.ndarray:
    """Chance the next shopper who tries each code at day t gets a discount."""
    alive = (w.code_birth <= t) & (t < w.code_death)
    fit = np.where(w.code_conditional, w.p.conditional_fit, 1.0)
    return alive * fit


def health(score: np.ndarray, p: Params) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-(p.prior_log_odds + score)))


@dataclass
class DayLog:
    day: int
    high_codes: int
    true_accuracy_high: float          # mean works-probability of high-tier codes
    fleet_successes_high: int
    fleet_failures_reported_high: int


@dataclass
class Run:
    world: World
    score: np.ndarray                  # evidence score per code at the end
    days: list[DayLog] = field(default_factory=list)
    # For each day after burn-in: which codes were high-tier and their works-probability.
    high_masks: list[np.ndarray] = field(default_factory=list)
    works: list[np.ndarray] = field(default_factory=list)
    fleet_succ: list[np.ndarray] = field(default_factory=list)   # per code, per day
    fleet_fail_reported: list[np.ndarray] = field(default_factory=list)


def simulate(p: Params, seed: int = 0) -> Run:
    """Run the world day by day; every evidence stream decays with its code type."""
    rng = np.random.default_rng(seed)
    w = make_world(p, rng)
    n = len(w.code_type)
    decay = np.exp(-1.0 / np.asarray(p.decay_days)[w.code_type])
    score = np.zeros(n)
    plat = w.merchant_platform[w.code_merchant]
    pop = w.merchant_popularity[w.code_merchant]
    spam = w.merchant_spam[w.code_merchant]
    block = np.asarray(p.bot_block)[plat]
    berr = np.asarray(p.bot_error)[plat]
    run = Run(w, score)
    for day in range(-p.burn_in_days, p.horizon_days):
        t = float(day)
        if p.drift_day is not None and day == p.drift_day and p.drift_kill_share > 0:
            hit = (np.isin(plat, np.atleast_1d(p.drift_platform)) & (w.code_birth <= t)
                   & (t < w.code_death) & (rng.random(n) < p.drift_kill_share))
            w.code_death[hit] = t
        born = w.code_birth <= t
        alive = born & (t < w.code_death)
        pw = works_probability(w, t)
        score *= decay
        score[~born] = 0.0

        # Automated checkout tests: they see whether the code exists and
        # functions, not whether it fits a given cart (a conditional code that
        # is alive reads as working, as the whitepaper says).
        tested = born & (rng.random(n) < np.asarray(p.bot_rate)[w.code_type]) & (rng.random(n) >= block)
        report = alive.copy()
        flip = rng.random(n) < berr
        report = np.where(flip, ~report, report)
        if p.drift_day is not None and day >= p.drift_day:
            drifted = np.isin(plat, np.atleast_1d(p.drift_platform)) & ~alive & (rng.random(n) < p.drift_false_pass)
            report = report | drifted
        score += np.where(tested, np.where(report, p.bot_weight, -p.bot_fail_weight), 0.0)

        # Human verifiers try the code on their own cart and vote.
        voted = born & (rng.random(n) < p.human_rate)
        tier = rng.choice(3, size=n, p=p.tier_share)
        ok = rng.random(n) < pw
        right = rng.random(n) < np.asarray(p.tier_accuracy)[tier]
        vote = np.where(right, ok, ~ok)
        wt = np.asarray(p.tier_weight)[tier]
        score += np.where(voted, np.where(vote, wt, -wt), 0.0)

        # Spam: anonymous "it works" posts on dead codes at some merchants.
        spammed = born & ~alive & spam & (rng.random(n) < p.spam_rate)
        score += np.where(spammed, p.spam_weight, 0.0)

        np.clip(score, *p.score_clip, out=score)
        h = health(score, p)
        shown = born & (h >= p.show_threshold)
        high = born & (h >= p.high_threshold)

        # Fleet: real checkouts by extension users, only on codes they are shown.
        # A success is always reported; a failure only sometimes (the shopper
        # may just leave). This is the assumption the experiments sweep.
        tries = rng.poisson(np.where(shown, p.fleet_rate * pop * h, 0.0))
        succ = rng.binomial(tries, pw)
        fail = tries - succ
        fail_rep = rng.binomial(fail, p.fleet_failure_capture)
        score += p.fleet_weight * (np.minimum(succ, p.fleet_cap) - np.minimum(fail_rep, p.fleet_cap))

        if day >= 0:
            run.days.append(
                DayLog(
                    day,
                    int(high.sum()),
                    float(pw[high].mean()) if high.any() else float("nan"),
                    int(succ[high].sum()),
                    int(fail_rep[high].sum()),
                )
            )
            run.high_masks.append(high.copy())
            run.works.append(pw.copy())
            run.fleet_succ.append(succ.astype(np.int32))
            run.fleet_fail_reported.append(fail_rep.astype(np.int32))
    run.score = score
    return run


def final_health(run: Run) -> np.ndarray:
    return health(run.score, run.world.p)


DECAY_NAMES = ("SLOW", "MODERATE", "FAST")


def export_packets(run: Run, path: str, window: int = 14, min_health: float = 0.2) -> int:
    """Write the last day as Proof Packets (JSON Lines), the shape the CLI reads.

    Only codes with some standing are written (health >= min_health), as a
    production export would list codes, not every dead string ever seen.
    """
    import json

    w, p = run.world, run.world.p
    h = final_health(run)
    T = p.horizon_days - 1
    born = w.code_birth <= T
    succ = np.sum(run.fleet_succ[-window:], axis=0)
    fail = np.sum(run.fleet_fail_reported[-window:], axis=0)
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for i in np.flatnonzero(born & (h >= min_health)):
            pkt = {
                "code": f"C{i:06d}",
                "merchant": f"m{w.code_merchant[i]:05d}.example",
                "verdict": "VERIFIED" if h[i] >= p.show_threshold else "UNVERIFIED",
                "confidence": round(float(h[i]), 4),
                "evidence": {
                    "fleet_signal": {"recent_successes": int(succ[i]), "recent_failures": int(fail[i])},
                    "health": {"score": round(float(h[i]), 4), "decay_rate": DECAY_NAMES[w.code_type[i]]},
                },
            }
            f.write(json.dumps(pkt) + "\n")
            n += 1
    return n


def try_codes(run: Run, codes: list[str], seed: int = 0) -> list[int]:
    """Stand-in for the robots or verifiers who try each planned code once."""
    rng = np.random.default_rng(seed)
    pw = run.works[-1]
    idx = np.array([int(c[1:]) for c in codes])
    return (rng.random(len(idx)) < pw[idx]).astype(int).tolist()

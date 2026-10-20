"""Figures for the README, from results/*.json (run examples/run_all.py first).

    uv run --extra figures python examples/make_figures.py
"""

from __future__ import annotations

import json
import os

import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(__file__)
RES = os.path.join(HERE, "..", "results")
FIG = os.path.join(HERE, "..", "figures")
INK, MUTED, BLUE, ORANGE, GREEN, RED = "#18202c", "#6b7280", "#1d4ed8", "#c2410c", "#16803d", "#dc2626"


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=INK)
    ax.grid(axis="y", color="#e5e7eb", lw=0.8)
    ax.set_axisbelow(True)


def fleet_bias():
    fb = json.load(open(os.path.join(RES, "fleet_bias.json")))
    qs = sorted(fb, key=float)
    x = np.array([float(q) for q in qs])
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    for key, color, label in (("fleet_accuracy", ORANGE, "what the fleet reports"),
                              ("audit_accuracy", BLUE, "random audit, 400 codes"),
                              ("true_accuracy", INK, "true accuracy")):
        m = np.array([fb[q][key]["mean"] for q in qs])
        lo = np.array([fb[q][key]["min"] for q in qs])
        hi = np.array([fb[q][key]["max"] for q in qs])
        ax.plot(x, m, "-o", color=color, label=label, lw=2, ms=5)
        ax.fill_between(x, lo, hi, color=color, alpha=0.12)
    ax.axvline(0.3, color=MUTED, ls=":", lw=1)
    ax.set_xlabel("share of failed checkouts the fleet ever reports")
    ax.set_ylabel("accuracy of high-tier codes")
    ax.set_title("The fleet overstates what is shown; a random audit does not", color=INK, loc="left")
    style(ax)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fleet_bias.png"), dpi=160)


def drift():
    d = json.load(open(os.path.join(RES, "drift_alarm.json")))
    r = d["drift"][0]
    days = np.arange(len(r["true_curve"]))
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(days, r["true_curve"], color=INK, lw=2, label="true accuracy of high-tier codes")
    ax.plot(days, r["fleet_curve"], color=ORANGE, lw=2, label="fleet success rate (7 days)")
    ax.axhline(0.85, color=MUTED, ls="--", lw=1, label="accuracy floor 0.85")
    ax.axvline(r["drift_day"], color=RED, lw=1, alpha=0.6)
    ax.text(r["drift_day"] + 0.5, 0.52, "site update:\ncodes die, bots\nread errors as success", color=RED, fontsize=8)
    if r["change_alarm_day"] is not None:
        ax.plot([r["change_alarm_day"]], [0.85], "v", color=BLUE, ms=11, label=f"audit alarm (day {r['change_alarm_day']})")
    ax.set_ylim(0.5, 1.01)
    ax.set_xlabel("day")
    ax.set_ylabel("accuracy")
    ax.set_title("A silent break: the audit alarm fires in a day, the fleet never does", color=INK, loc="left")
    style(ax)
    ax.legend(frameon=False, loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "drift_alarm.png"), dpi=160)


def tiers():
    tc = json.load(open(os.path.join(RES, "tier_certificates.json")))
    ev = [t["types"]["evergreen"] for t in tc]
    fixed = [e["fixed_rule_true_accuracy"] for e in ev]
    cert = [e["certified_true_accuracy"] for e in ev]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.scatter(np.zeros(len(fixed)) + np.linspace(-0.08, 0.08, len(fixed)), fixed, color=ORANGE, s=30,
               label="one line for all codes (health >= 0.8)")
    ax.scatter(np.ones(len(cert)) + np.linspace(-0.08, 0.08, len(cert)), cert, color=BLUE, s=30,
               label="certified line for evergreen codes")
    ax.axhline(0.95, color=MUTED, ls="--", lw=1)
    ax.text(1.25, 0.951, "target 0.95", color=MUTED, fontsize=8)
    ax.set_xticks([0, 1], ["fixed rule", "certified"])
    ax.set_xlim(-0.5, 1.6)
    ax.set_ylabel("true accuracy of codes shown as high")
    ax.set_title("Evergreen codes, 10 runs: the certified line holds the target", color=INK, loc="left")
    style(ax)
    ax.legend(frameon=False, loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "tiers.png"), dpi=160)


def applicability():
    path = os.path.join(RES, "applicability_eval.json")
    if not os.path.exists(path):
        return
    ev = json.load(open(path))
    s = ev["by_stratum"]
    groups = [("codes with a condition", s["conditional"]), ("all codes, re-weighted to 25.5%", None)]
    pw = s.get("population_weighted", {})
    labels = ["today: functional\nmeans it applies", "Claude reads\nthe terms", "GPT reads\nthe terms", "both agree\n(settled share)"]
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.9), sharey=True)
    for ax, (title, d) in zip(axes, groups):
        if d is not None:
            vals = [d["todays_rule"], d["claude_alone"], d["gpt_alone"], d["gate_accuracy"]]
            share = d["gate_settled_share"]
        else:
            c, u = s["conditional"], s["unconditional"]
            w = 0.255
            vals = [pw["todays_rule"], pw["claude_alone"], pw["gpt_alone"],
                    w * c["gate_accuracy"] + (1 - w) * u["gate_accuracy"]]
            share = pw["gate_settled_share"]
        colors = [ORANGE, MUTED, MUTED, BLUE]
        bars = ax.bar(range(4), vals, color=colors, width=0.62)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.1%}", ha="center", color=INK, fontsize=9)
        ax.text(3, 0.08, f"settles\n{share:.0%}", ha="center", color="white", fontsize=8)
        ax.set_xticks(range(4), labels, fontsize=8)
        ax.set_ylim(0, 1.08)
        ax.set_title(title, color=INK, fontsize=10, loc="left")
        style(ax)
    axes[0].set_ylabel("verdicts right, per cart")
    fig.suptitle("Will this code work for this cart?", color=INK, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "applicability.png"), dpi=160)


if __name__ == "__main__":
    os.makedirs(FIG, exist_ok=True)
    fleet_bias()
    drift()
    tiers()
    applicability()
    print("figures written to", os.path.abspath(FIG))

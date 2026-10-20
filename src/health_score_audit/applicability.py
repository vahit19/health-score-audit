"""Will this code work for this cart? Promo terms -> machine-readable conditions -> verdict.

"Anatomy of a Verdict" names this as the next step for SimplyCodes: today a bot
confirms a code exists and functions; it does not confirm the code applies to a
given cart. The whitepaper describes the target as a "constitutional model"
for promotions: structured conditions (minimum spend, category inclusions and
exclusions, user eligibility) instead of free text.

This module does that in three steps and measures each one:

1. Terms. Promo terms are written in natural language from conditions we know
   (so ground truth is exact) by a model from one family (Qwen).
2. Extraction. Two models from two other families (Claude and GPT) read each
   terms text and return the conditions as JSON. No model reads text its own
   family wrote, following the self-preference rule from verdict-gate.
3. Verdict per cart. A plain rule engine applies the extracted conditions to a
   cart. When the two extractions give the same verdict for a cart, the
   machine settles it; when they disagree, it abstains and the code is sent to
   a bot checkout with that cart. The settled verdicts are certified with
   verdict-gate's bound, and compared with today's rule ("functional means it
   applies").

Every model call is cached in results/ so the numbers regenerate offline.
"""

from __future__ import annotations

import json
import time
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

import numpy as np

CATEGORIES = ("apparel", "shoes", "electronics", "beauty", "home", "gift_cards", "sale_items", "clearance")
GENERATOR = "qwen/qwen3.8-flash"
EXTRACTORS = ("anthropic/claude-haiku-5.5", "openai/gpt-5.6-luna")


@dataclass
class Conditions:
    percent_off: int | None = None
    amount_off: float | None = None
    min_subtotal: float | None = None
    excluded_categories: list[str] = field(default_factory=list)
    included_categories: list[str] = field(default_factory=list)   # empty means all
    new_customers_only: bool = False

    @staticmethod
    def from_json(d: dict) -> "Conditions":
        def num(x):
            try:
                return None if x in (None, "", "null") else float(x)
            except (TypeError, ValueError):
                return None

        def cats(x):
            return sorted({str(c).strip().lower() for c in (x or []) if str(c).strip().lower() in CATEGORIES})

        pct = num(d.get("percent_off"))
        return Conditions(
            percent_off=int(pct) if pct is not None else None,
            amount_off=num(d.get("amount_off")),
            min_subtotal=num(d.get("min_subtotal")),
            excluded_categories=cats(d.get("excluded_categories")),
            included_categories=cats(d.get("included_categories")),
            new_customers_only=bool(d.get("new_customers_only", False)),
        )


@dataclass
class Cart:
    items: list[tuple[str, float]]     # (category, price)
    new_customer: bool


def applies(c: Conditions, cart: Cart) -> bool:
    """Does the merchant accept the code for this cart?

    Excluded items do not count toward the minimum, and at least one eligible
    item must be in the cart. Eligibility of the customer is checked first.
    """
    if c.new_customers_only and not cart.new_customer:
        return False
    eligible = [
        p for cat, p in cart.items
        if cat not in c.excluded_categories and (not c.included_categories or cat in c.included_categories)
    ]
    if not eligible:
        return False
    if c.min_subtotal is not None and sum(eligible) < c.min_subtotal:
        return False
    return True


PRIMARY = ("apparel", "shoes", "electronics", "beauty", "home")


def random_conditions(rng: np.random.Generator, conditional: bool = True,
                      primary: str = "apparel") -> Conditions:
    """Draw a code the way SimplyCodes reports codes are (published live counts, Oct 2026).

    91% of codes take a percentage off (median 10%), 7.5% a dollar amount (median
    $14). Among codes with a condition: item scoping 55%, minimum spend 37%
    (median $99, 37% at $50 or under; 8.6x as common on dollar-off codes),
    membership 6%, new customers 1.6%. Gift-card and sale exclusions are the
    most common carve-outs in the terms text. A code can carry several.
    """
    c = Conditions()
    dollar = rng.random() < 0.076
    if dollar:
        c.amount_off = float(rng.choice([5, 10, 14, 15, 20, 25, 50], p=[.1, .2, .2, .15, .15, .1, .1]))
    else:
        c.percent_off = int(rng.choice([5, 10, 15, 20, 25, 30, 40, 50], p=[.08, .37, .17, .17, .09, .06, .04, .02]))
    if not conditional:
        if rng.random() < 0.3:
            c.excluded_categories = ["gift_cards"]
        return c
    kind = rng.choice(["scope", "min", "member"], p=[0.55, 0.37, 0.08])
    if kind == "scope" or rng.random() < 0.15:
        pool = [x for x in PRIMARY if x != primary]
        c.included_categories = sorted({primary if rng.random() < 0.5 else str(rng.choice(pool))})
    if kind == "min" or rng.random() < (0.25 if dollar else 0.05):
        c.min_subtotal = float(rng.choice([25, 35, 50, 75, 100, 150, 200], p=[.12, .10, .15, .13, .25, .15, .10]))
    if kind == "member":
        c.new_customers_only = True        # membership and new-customer gates both check who the shopper is
    if rng.random() < 0.45:
        k = int(rng.integers(1, 3))
        c.excluded_categories = sorted(rng.choice(["gift_cards", "sale_items", "clearance"], size=k, replace=False).tolist())
    return c


def random_cart(rng: np.random.Generator, primary: str = "apparel") -> Cart:
    """1-5 items, mostly from the store's main category, some on sale; about $90 median."""
    k = int(rng.integers(1, 6))
    items = []
    for _ in range(k):
        r = rng.random()
        cat = primary if r < 0.65 else ("sale_items" if r < 0.8 else str(rng.choice(CATEGORIES)))
        items.append((cat, float(np.round(rng.lognormal(3.4, 0.6), 2))))
    return Cart(items, bool(rng.random() < 0.3))


# ---------------------------------------------------------------- model calls

def _call(model: str, system: str, user: str, temperature: float = 0.0, max_tokens: int = 600,
          reasoning: bool = True) -> str:
    key = os.environ["OPENROUTER_API_KEY"]
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        **({} if reasoning else {"reasoning": {"enabled": False}}),
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read().decode())
            return d["choices"][0]["message"]["content"] or ""
        except Exception:
            if attempt == 3:
                return ""
            time.sleep(2 ** attempt + 1)   # rate limits: back off and retry
    return ""


GEN_SYSTEM = (
    "You write the fine print for an online store's promo code, the way real retailers do. "
    "Write one paragraph of 2 to 5 sentences. State every condition you are given, in your own words, "
    "and do not add any other condition that changes who can use the code or which carts qualify. "
    "You may add harmless boilerplate (one use per customer, cannot be combined, expiry date, store name). "
    "Do not use bullet points or the words 'condition' or 'category'. Output only the paragraph."
)

GEN_SYSTEM_HARD = (
    "You write the dense legal fine print for an online store's promo code, the way large retailers do. "
    "Write one paragraph of 4 to 7 sentences. State every condition you are given, but in indirect, legalistic "
    "wording (for example 'merchandise subtotal, before taxes, shipping and previously applied discounts' or "
    "'first-time purchasers' or 'items designated as final sale'). Add at least two distracting numbers that are NOT "
    "conditions on which carts qualify, such as a free-shipping threshold, a maximum savings cap, a reward points "
    "amount, an expiry date, or a different promotion that does not apply. Never add a condition that changes who "
    "can use this code or which carts qualify. No bullet points. Output only the paragraph."
)

EXTRACT_SYSTEM = (
    "You read the fine print of a promo code and return its conditions as JSON with exactly these keys: "
    "percent_off (number or null), amount_off (number or null), min_subtotal (number or null; the minimum "
    "order or purchase amount in dollars), excluded_categories (list), included_categories (list; empty if the "
    "code applies to everything not excluded), new_customers_only (true or false). Categories must come from: "
    + ", ".join(CATEGORIES)
    + ". Map wording to the closest of these (for example 'items already on sale' -> sale_items, "
    "'gift certificates' -> gift_cards, 'final sale' or 'clearance' -> clearance, 'footwear' -> shoes). "
    "Ignore anything that does not decide whether a cart qualifies (expiry, one use, cannot combine). "
    "Return only the JSON object."
)


def describe(c: Conditions) -> str:
    parts = []
    parts.append(f"{c.percent_off}% off" if c.percent_off else f"${c.amount_off:g} off")
    if c.min_subtotal:
        parts.append(f"requires a minimum purchase of ${c.min_subtotal:g} (excluded items do not count toward it)")
    if c.included_categories:
        parts.append("only valid on " + ", ".join(x.replace("_", " ") for x in c.included_categories))
    if c.excluded_categories:
        parts.append("not valid on " + ", ".join(x.replace("_", " ") for x in c.excluded_categories))
    parts.append("new customers only" if c.new_customers_only else "open to all customers")
    return "; ".join(parts)


def _parse_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


KEYWORDS = {
    "gift_cards": ("gift",), "sale_items": ("sale",), "clearance": ("clearance", "final sale", "final-sale"),
    "electronics": ("electronic",), "beauty": ("beauty", "cosmetic", "skincare", "makeup"),
    "apparel": ("apparel", "clothing", "clothes"), "shoes": ("shoe", "footwear"), "home": ("home",),
}


def terms_state_all(c: Conditions, text: str) -> bool:
    """Plain checks that the written terms carry every condition (the truth must be in the text).

    Every number appears, every category has one of its words, "new" appears for
    new-customer codes, and the paragraph is complete. A terms text that fails
    is rewritten; this keeps the ground truth honest.
    """
    t = text.lower().replace(",", "")
    if len(t) < 40 or not t.rstrip().endswith((".", "!", ")")):
        return False
    nums = [c.min_subtotal, c.amount_off, c.percent_off]
    if any(x is not None and f"{x:g}" not in t for x in nums):
        return False
    for cat in c.excluded_categories + c.included_categories:
        if not any(k in t for k in KEYWORDS[cat]):
            return False
    if c.new_customers_only and not any(k in t for k in ("new", "first", "member")):
        return False
    return True


def build_corpus(n: int, seed: int, cache: str, workers: int = 4, tries: int = 4, hard: bool = False,
                 conditional_share: float = 0.6) -> list[dict]:
    """Terms texts with known conditions, written by GENERATOR and checked. Cached."""
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f]
        return rows[:n]          # texts that failed the check were dropped, so there can be fewer than n
    rng = np.random.default_rng(seed)
    primary = [str(rng.choice(PRIMARY)) for _ in range(n)]
    cond = [bool(rng.random() < conditional_share) for _ in range(n)]
    truth = [random_conditions(rng, c, p) for c, p in zip(cond, primary)]

    def write(c: Conditions) -> tuple[str, int]:
        for k in range(tries):
            text = _call(GENERATOR, GEN_SYSTEM_HARD if hard else GEN_SYSTEM, describe(c),
                         temperature=0.9, max_tokens=600, reasoning=False).strip()
            if terms_state_all(c, text):
                return text, k + 1
        return "", tries

    with ThreadPoolExecutor(workers) as ex:
        out = list(ex.map(write, truth))
    rows = [dict(id=i, truth=asdict(c), terms=t, attempts=a, hard=hard, primary=primary[i], conditional=cond[i])
            for i, (c, (t, a)) in enumerate(zip(truth, out)) if t]
    with open(cache, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return rows


def extract_all(corpus: list[dict], cache: str, workers: int = 4) -> dict[str, list[dict | None]]:
    """Each extractor reads each terms text once. Cached."""
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            d = json.load(f)
        if all(len(d.get(m, [])) == len(corpus) for m in EXTRACTORS):
            return d
    out = {}
    for m in EXTRACTORS:
        with ThreadPoolExecutor(workers) as ex:
            texts = list(ex.map(lambda r: _call(m, EXTRACT_SYSTEM, r["terms"]), corpus))
        out[m] = [_parse_json(t) for t in texts]
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


def evaluate(corpus: list[dict], extracted: dict[str, list[dict | None]], carts_per_code: int = 20,
             seed: int = 1, target: float = 0.95) -> dict:
    """Per-cart verdicts: today's rule, each extractor alone, and the two-family agreement gate."""
    from verdict_gate import audit_bound

    rng = np.random.default_rng(seed)
    a_name, b_name = EXTRACTORS
    rows = []
    field_hits = {m: {k: 0 for k in ("min_subtotal", "excluded_categories", "included_categories", "new_customers_only")}
                  for m in EXTRACTORS}
    for i, r in enumerate(corpus):
        truth = Conditions(**r["truth"])
        ext = {}
        for m in EXTRACTORS:
            d = extracted[m][i]
            ext[m] = Conditions.from_json(d) if d else None
            if ext[m] is not None:
                for k in field_hits[m]:
                    field_hits[m][k] += int(getattr(ext[m], k) == getattr(truth, k))
        for _ in range(carts_per_code):
            cart = random_cart(rng, r.get("primary", "apparel"))
            t = applies(truth, cart)
            va = applies(ext[a_name], cart) if ext[a_name] else None
            vb = applies(ext[b_name], cart) if ext[b_name] else None
            rows.append((t, va, vb, bool(r.get("conditional", True))))
    t = np.array([x[0] for x in rows])
    va = np.array([x[1] if x[1] is not None else (not x[0]) for x in rows])   # failed parse counts as wrong
    vb = np.array([x[2] if x[2] is not None else (not x[0]) for x in rows])
    agree = va == vb
    n = len(t)
    cond = np.array([x[3] for x in rows])

    def acc(pred, mask=None):
        m = np.ones(n, bool) if mask is None else mask
        k = int((pred[m] != t[m]).sum())
        a, lo = audit_bound(k, int(m.sum()), 0.05)
        return dict(verdicts=int(m.sum()), accuracy=a, lower_bound=lo)

    return dict(
        codes=len(corpus),
        carts_per_code=carts_per_code,
        verdicts=n,
        share_of_carts_where_code_applies=float(t.mean()),
        todays_rule_functional_means_applies=acc(np.ones(n, bool)),
        extractor_alone={m.split("/")[1]: acc(v) for m, v in ((a_name, va), (b_name, vb))},
        agreement_gate=dict(settled_share=float(agree.mean()), **acc(va, agree)),
        abstained_to_bot=int((~agree).sum()),
        field_accuracy={m.split("/")[1]: {k: v / len(corpus) for k, v in f.items()} for m, f in field_hits.items()},
        target=target,
        by_stratum=_strata(t, va, vb, agree, cond),
    )


def _strata(t, va, vb, agree, cond, population_conditional_share: float = 0.255) -> dict:
    """Accuracy for codes with and without conditions, and reweighted to the published 25.5% mix."""
    out = {}
    for name, m in (("conditional", cond), ("unconditional", ~cond)):
        if not m.any():
            continue
        out[name] = dict(
            verdicts=int(m.sum()),
            todays_rule=float((t[m]).mean()),
            claude_alone=float((va[m] == t[m]).mean()),
            gpt_alone=float((vb[m] == t[m]).mean()),
            gate_settled_share=float(agree[m].mean()),
            gate_accuracy=float((va[m & agree] == t[m & agree]).mean()) if (m & agree).any() else None,
        )
    if "conditional" in out and "unconditional" in out:
        w = population_conditional_share
        out["population_weighted"] = {
            k: w * out["conditional"][k] + (1 - w) * out["unconditional"][k]
            for k in ("todays_rule", "claude_alone", "gpt_alone", "gate_settled_share")
        }
    return out

"""Question 4: will this code work for this cart? (offline from the cached model calls in data/)

    uv run python examples/run_applicability.py            # uses data/promo_terms.jsonl and data/extractions.json
    OPENROUTER_API_KEY=... uv run python examples/run_applicability.py --fresh 200   # regenerate (about $0.30)
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from health_score_audit.applicability import build_corpus, evaluate, extract_all  # noqa: E402

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
RES = os.path.join(HERE, "..", "results")


def main() -> None:
    fresh = "--fresh" in sys.argv
    n = int(sys.argv[sys.argv.index("--fresh") + 1]) if fresh else 200
    terms = os.path.join(DATA, "promo_terms.jsonl")
    ext = os.path.join(DATA, "extractions.json")
    if fresh:
        for p in (terms, ext):
            if os.path.exists(p):
                os.remove(p)
    corpus = build_corpus(n, seed=11, cache=terms, hard=True)
    extracted = extract_all(corpus, cache=ext)
    ev = evaluate(corpus, extracted, carts_per_code=20)
    os.makedirs(RES, exist_ok=True)
    json.dump(ev, open(os.path.join(RES, "applicability_eval.json"), "w"), indent=1)
    s = ev["by_stratum"]
    print(f"{ev['codes']} codes, {ev['verdicts']} verdicts")
    print("codes with a condition: today's rule {todays_rule:.1%}, Claude {claude_alone:.1%}, GPT {gpt_alone:.1%}, "
          "gate settles {gate_settled_share:.1%} at {gate_accuracy:.1%}".format(**s["conditional"]))
    g = ev["agreement_gate"]
    print(f"all verdicts: gate settles {g['settled_share']:.1%} at {g['accuracy']:.1%} (>= {g['lower_bound']:.1%}); "
          f"{ev['abstained_to_bot']} sent to a bot")


if __name__ == "__main__":
    main()

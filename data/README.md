# Data

Three files, all regenerable from the code in this repository.

## `promo_terms.jsonl`: promo fine print with known conditions

One promo code per line. Each record has the conditions the code really has (`truth`) and the fine print a model wrote for them (`terms`).

| Field | Meaning |
|---|---|
| `truth` | `percent_off`, `amount_off`, `min_subtotal` (dollars; excluded items do not count toward it), `excluded_categories`, `included_categories` (empty: everything not excluded), `new_customers_only` (also stands for membership gates) |
| `terms` | the fine print, written by `qwen/qwen3.8-flash` in dense retail legal style, with at least two distracting numbers that are not conditions (a free-shipping threshold, a savings cap, an expiry date, reward points) |
| `conditional` | whether the code carries a condition beyond an end date |
| `primary` | the store's main category, used to fill carts |
| `attempts` | how many drafts it took before the fine print passed the check below |

How the conditions are drawn follows SimplyCodes' published counts ([CALIBRATION.md](../CALIBRATION.md)): 92% percent-off with a median of 10%, minimum spends with a median near $100, item scoping as the most common condition. The sample over-weights codes with conditions (60% against 25.5% in the population) so the hard cases are measured with enough data; results are re-weighted to 25.5%.

**Ground truth is checked, not assumed.** Before a terms text is kept, a plain check confirms that every number in the conditions appears in it, every category has one of its words, identity gates are named, and the paragraph is complete. Texts that fail are rewritten (up to four drafts) or dropped. In a first pilot without this check, the generator silently dropped a $25 minimum and cut a paragraph short, and both extractors were then scored "wrong" for reading the text correctly.

**What it is not.** These are not scraped retailer terms: the wording is a model's, so it can be cleaner or stranger than real fine print. The conditions, the distractors and the legal register are modeled on real terms (QVC, HSN, Kelty, Abercrombie and others publish theirs).

## `extractions.json`: what each model read

For each terms text, the JSON conditions returned by `anthropic/claude-haiku-5.5` and `openai/gpt-5.6-luna` (temperature 0). Neither model family wrote the texts it reads.

## `proof_packets_sample.jsonl`: Proof Packets from the simulator

The last simulated day as Proof Packets, in the shape published in "Anatomy of a Verdict", for trying the `hsa` commands. Codes and merchants are synthetic.

## Known issue in the answer key

The generator was told not to add conditions, but it often added boilerplate exclusions ("clearance and final-sale items") to the fine print. The check above catches dropped conditions, not added ones. In 98 of Claude's 101 excluded-category disagreements with `truth` (99 of GPT's 105), the extra exclusion is written in the text, so the model read it correctly and the record's `truth` is incomplete. Verdict accuracies computed against `truth` are therefore lower bounds.

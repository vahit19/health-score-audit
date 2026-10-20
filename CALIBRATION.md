# Where each number in the simulator comes from

Every parameter is either taken from a figure SimplyCodes / Product.ai has published, or marked as an assumption. Assumptions that move a result are swept in the experiments. Figures were read on 20 October 2026; the SimplyCodes live-data pages refresh daily, so later readings will differ slightly.

## Published figures used

| Parameter | Value used | Published figure | Source |
|---|---|---|---|
| Code lifetimes (`type_share`, `mean_lifetime_days`) | 3-type exponential mixture: 26.1% evergreen (mean 104.5 days), 34.9% regular (15.7 days), 39.0% flash (1.77 days); mixture mean 33.3 days | 23,107 codes: 18.2% die the same day, 21.3% in 1–3 days, 12.2% in 4–7 days, 10.7% in 1–2 weeks, 12.0% in 2–4 weeks, 9.7% in 1–2 months, 4.9% in 2–3 months, 11.1% after 3+ months; mean 33 days | [How Long Do Promo Codes Last?](https://simplycodes.com/blog/how-long-do-promo-codes-last) |
| Code types and decay clocks | evergreen / regular / flash, each with its own decay | "Evergreen codes decay slowly … Regular codes … within weeks … Flash codes … within days or hours" | [Anatomy of a Verdict](https://product.ai/research/anatomy-of-a-verdict/) |
| Share of codes with a condition (`conditional_share`) | 25.5% | 25.5% of 9,533,407 tracked codes carry a condition beyond an end date | [How Many Promo Codes Have Restrictions?](https://simplycodes.com/blog/live-data/how-many-promo-codes-have-restrictions) |
| Mix of conditions (applicability corpus) | item scoping 55%, minimum spend 37%, identity gates 8% of conditional codes | item scoping 1,041,526 codes; minimum spend 695,124; membership 112,673; new-customer-only 30,195 | same page; [What Does "New Customers Only" Mean?](https://simplycodes.com/blog/live-data/what-does-new-customer-only-mean) |
| Minimum spend values | median $100 in the draw, 37% at $50 or under | median $99 across 48,729 live codes with a dollar threshold; 37.2% at $50 or under | [The Minimum Order Behind a Promo Code](https://simplycodes.com/blog/live-data/average-minimum-order-by-category) |
| Discount form | 92.4% percent-off (median 10%), 7.6% dollar-off (median $14); minimum spend far more common on dollar-off codes | 91.37% percent-off, 7.54% dollar-off; medians 10% and $14; minimum spend on 10.31% of dollar-off vs 1.20% of percent-off codes | [Are Promo Codes Percentage Off or Dollars Off?](https://simplycodes.com/blog/live-data/percent-off-vs-dollar-off-codes) |
| Common exclusions in terms text | gift cards, sale items, clearance | gift cards excluded by 487 retailers, sale and clearance by 387 | [Do Promo Codes Work on Gift Cards?](https://simplycodes.com/blog/live-data/do-promo-codes-work-on-gift-cards) |
| Human verifier accuracy (`tier_accuracy`) | tiers 99.5% / 98.5% / 94%, average 97.8% | "10,000+ verifiers … 98% accuracy" | methodology note on the live-data pages |
| Evidence streams | bots, trust-weighted human votes with blind consensus, fleet checkouts; score saturates, a recent failure drops health | three-layer verification stack, trust tiers, "a recent failure drops health immediately" | [Anatomy of a Verdict](https://product.ai/research/anatomy-of-a-verdict/) |
| Proof Packet fields read by the CLI | `code`, `merchant`, `verdict`, `confidence`, `evidence.fleet_signal`, `evidence.health.decay_rate` | the Proof Packet example | [Anatomy of a Verdict](https://product.ai/research/anatomy-of-a-verdict/) |
| Silent breaks | a site update kills codes and breaks the bots' reading | "They break their own cart logic during site updates. A code that worked Monday can die Tuesday" | [Anatomy of a Verdict](https://product.ai/research/anatomy-of-a-verdict/) |

## Cross-checks (not fitted, for comparison)

| What the simulator gives | Published |
|---|---|
| 82.3% of the codes born in the simulated window are dead on its last day (not fitted) | 78.9% of 9.5M tracked codes no longer work ([Dead-Code Census](https://simplycodes.com/blog/live-data/what-percent-of-coupon-codes-are-expired)); "40–60% of codes on the public internet are dead, restricted, or misleading" |

## Assumptions (nothing published)

| Parameter | Value | Why it matters | Swept? |
|---|---|---|---|
| `fleet_failure_capture`: share of failed checkouts the fleet reports | 0.3 | decides how far the fleet overstates accuracy | yes, 0.1–1.0 (`fleet_bias.json`) |
| `conditional_fit`: chance a random cart meets a code's condition | 0.35 | sets the accuracy ceiling of "functional means it applies" | no; the applicability experiment measures it on carts directly |
| Bot test rate, block rate and error rate per platform | see `Params` | how fast health reacts | no |
| Signal weights, prior, clip, decay clocks, display tiers | see `Params` | the health score itself is a stand-in, not Product.ai's | no |
| Platform mix (adapter / heuristic / AI navigation) | 60 / 30 / 10 | who is hit by a site update | no |
| Drift: share of codes a site update kills, and that bots misread | 40%, 100% on 90% of merchants | how deep the break is | no |
| Shopper carts: 1–5 items, about $90 median, 65% from the store's main category, 30% new customers | | how often conditions bind | no |

## What this does not show

The health score, the weights and the bots are a model of the published architecture, not Product.ai's system. Results about the audit (the random sample's interval covers the truth, a certificate holds its target, the change alarm's false-alarm rate) depend only on drawing the audit at random and do not rely on these assumptions. Results about size (how far the fleet overstates, how many codes a certificate admits, how fast the alarm fires) do depend on them, and should be re-measured on Product.ai's own events.

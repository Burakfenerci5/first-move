# First Move — scoring model

The whole point of First Move is *which three*. This is the logic that decides.
It is deliberately simple and explainable — a rep should be able to read the
"why" line and agree in one second.

## The score

```
score = 0.30 · value  +  0.50 · urgency  +  0.20 · severity
```

Every component is normalized to `0.0 – 1.0`. Weights live in
`config/catalog.json → weights`. They are **robustness-calibrated on the sample
books, not fit to revenue outcomes** — see "How the weights were chosen" below.
Expect to revisit them once real usage data exists.

### value — how much money is on the line
By default this is **expected value**: `amount × (probability ÷ 100)`,
normalized against the largest expected value the rep owns. Set
`rules.use_expected_value: false` (or run `--no-ev`) to fall back to raw amount.
Expected value is why a 90%-likely $95K deal outranks a 50/50 $120K one — the
bigger sticker price loses to the surer money. Non-deal plays use a proxy: new
leads use `lead_proxy_value × count`; pipeline hygiene uses the largest deal
with a gap. Leader plays normalize money against the quarter's quota.

### urgency — how soon it matters
`urgency_from_days(days_to_deadline)`: overdue → `1.0`; then it decays linearly
to a floor of `0.15` across `urgency_horizon_days` (45). A few housekeeping
plays use a fixed urgency instead of a date (logging a call = `0.6`; a fresh
lead SLA = `0.85`) because they aren't deadline-driven.

### severity — how bad / how much
Play-specific: a stalled deal uses staleness (`days_since_activity ÷ stale_cap`);
hygiene uses `gap_count ÷ hygiene_gap_cap`; unlogged calls use
`count ÷ unlogged_call_cap`. All capped at `1.0`.

## The gates and rules

1. **Enabled only.** A play is eligible only if its mapped skill is
   `enabled: true` in the catalog. No dead-end buttons — if you can't act on
   it, you don't surface it.
2. **One card per type.** Each detector may emit several candidates (e.g. four
   deals have gone quiet); `select_top` keeps only the highest-scoring instance
   of each recommendation type, so the Top 3 stays varied.
3. **Persona filter.** The engine reads the book's `persona` and runs only that
   persona's detectors and recommendations. **Rep** plays work a book of
   opportunities, calls, and leads; **leader** plays work team rollups, the
   forecast, key deals, and account health. The two never mix in one Top 3.
4. **Quick-win guarantee** (`rules.guarantee_quick_win`). If nothing
   low-effort made the Top 3, the weakest slot is swapped for the best
   available quick win — so there's always one thing finishable in under a
   minute. (If a persona has no low-effort plays available, it no-ops.)
5. **Diversification** (`rules.diversify`, default **on**). The Top 3 avoids two
   cards about the same entity — account for most plays, rep for coaching.
   Portfolio-scoped plays (pipeline hygiene, forecast, team coverage) never
   block each other. Run `--no-diversify` to see the raw ranking. This is what
   keeps a second, lower play about an already-surfaced account out of the list.

## How the weights were chosen

We have no labeled closed-won outcomes yet, so the weights are **not** a
supervised fit — claiming otherwise would be dishonest. `scripts/calibrate.py`
calibrates them two defensible ways instead, and the numbers below come from
running it:

1. **Sensitivity.** Sweep every value/urgency/severity split that sums to 1.0
   (231 of them, 0.05 steps) and, per sample book, measure how stable the #1
   pick is. The rep headlines are robust: `deal_gone_quiet` (Jordan) and
   `untouched_new_leads` (Priya) each own the top slot across **81%** of the
   whole weight simplex — the exact weights barely move them. The leader
   headline is *not* robust: `team_pipeline_coverage` and `deal_needs_review`
   split the simplex almost 49/51, so which one leads is a genuine judgment call
   the weights can't settle. That one needs real outcome data, not a weight.

2. **Constraint satisfaction + robustness.** A short list of high-confidence
   expert judgments ("a $95K deal at 90% going cold should outrank generic
   pipeline hygiene"; "a call happening today should outrank logging an old
   one") are encoded as pairwise ordering constraints. We take the weights that
   maximize the *minimum* satisfied margin — the point farthest from any flip
   boundary — subject to keeping every signal in a product-sane range (value
   0.30–0.45, urgency 0.35–0.55, severity 0.15–0.30) so no signal gets zeroed
   out. That yields **0.30 / 0.50 / 0.20**.

The move from the original `0.40 / 0.35 / 0.25` guess to `0.30 / 0.50 / 0.20`
did **not** change a single Top-3 headline on any sample book. What it changed
is robustness: the weakest expert-judgment margin (call-today vs. log-an-old-call)
went from a knife-edge **+0.004** to a comfortable **+0.092** — the old weights
were one data jitter away from putting "log a call from last week" above "prep
the call you have this afternoon."

Deliberately left out of the constraints: the genuinely debatable calls (should
a quiet high-EV deal outrank a call happening today?). Those are exactly what
weights are meant to adjudicate, so hard-coding an answer would make the
calibration circular. The sensitivity map shows where they flip instead.

Re-run `python3 scripts/calibrate.py` any time — it grades whatever weights are
currently in the catalog, so it doubles as a regression check when you tune.

## Why this list, not a black box

Netflix never tells you *why* a title is recommended. Enterprise software must —
a rep won't act on a play they don't trust. Every card carries a `why` built
from the actual numbers (deal size, days quiet, count), so the recommendation
is auditable, not magic.

## From sample to live (later phases)

The detectors read plain record dicts whose shapes mirror Salesforce
`Opportunity` / `Task` / `Lead` fields. In Phase 2 the only thing that changes
is the *source*: instead of `data/sample_book.json`, the records come from a
per-user SOQL query over what the rep owns. The scoring, gates, and rules are
unchanged.

## Honest limits

- Weights are robustness-calibrated on three sample books, not fit to revenue
  outcomes (see "How the weights were chosen"). The rep headlines are stable
  across the weight space; the leader headline is a near-tie the weights can't
  settle — treat that one as directional until real outcome data exists.
- Expected value is only as good as `Opportunity.Probability`. If an org leaves
  stage probabilities at defaults (or reps don't maintain them), expected value
  is really just stage-weighted amount — better than raw amount, but not a
  calibrated win model.
- Leader `value` normalizes against quota, so a single large deal reads as a
  small fraction of the number. That's intentional (a $250K deal *is* a slice of
  a $2M quarter), but it means leader scores run lower than rep scores — never
  compare the two pools' absolute scores, only the ranking within a pool.
- Leading indicators (activity, hygiene, response time) are measured cleanly.
  Attributing closed revenue to a First Move play needs a proper cohort test;
  don't overclaim it from this engine alone.

---
name: first-move
description: >-
  Opens a seller's Claude session with their top 3 next-best plays from
  Salesforce instead of a blank prompt. Scans what they own, ranks by
  expected-value x urgency x severity, and routes each play to a Salesforce for
  Sales skill. Works for sales reps and sales leaders (managers). Use at the
  start of someone's day, on their first message, or when they ask "what should
  I focus on?" / invoke first-move. Phase 1 runs on bundled sample data —
  read-only, no Salesforce writes.
---

# First Move — Phase 1 (sample data)

## What this does
Instead of greeting a seller with a blank box, First Move opens with the
**top 3 things worth their attention right now**, drawn from their own book of
business — each one a real next-best play tied to a Salesforce for Sales skill.
It adapts to who is asking: a **rep** gets deal/call/lead plays; a **sales
leader** gets team-level plays (pipeline coverage, forecast gap, deal reviews).

## When to use
- **Automatically, at session start.** When installed as a plugin, a
  `SessionStart` hook (`hooks/hooks.json` → `scripts/session_start.sh`) runs the
  Turn-0 scan the moment a fresh session launches and injects the seller's top 3
  plays into context. Open with those three cards before anything else.
- The seller asks "what should I focus on?", "what's on my plate?", or similar.
- The seller runs the `/first-move:go` command, or explicitly invokes `first-move`.

The SessionStart hook is the closest thing to Turn 0 that Claude Code exposes
today: it fires before the seller's first message, so First Move leads rather
than waiting to be asked. True zero-touch (the assistant speaking with no
session action at all) remains a platform capability, not something this skill
forces.

## Data source: sample vs. live
- **Read-only.** First Move never writes to Salesforce during the scan. Writes
  only happen inside the mapped skill chains a button invokes (Phase 2 action
  layer, which needs the Salesforce for Sales skills via h360).
- **Sample data (default).** Reads a bundled book in `data/` — no org needed.
- **Live org (when a Salesforce connector is connected).** The same engine runs
  against a live book produced by `scripts/live_scan.py` from SOQL over the
  connector's `dispatch_readonly`. Follow `references/live-scan.md`, then
  `rank.py --book-path <live_book>`. The rep persona is fully wired from standard
  fields; confirm the connected org is the intended one before presenting.
- **Rep and leader personas.** The engine picks detectors from the book's
  `persona` field. Both run on sample data. The **live** rep scan is wired; the
  live **leader** scan (team rollups, forecast, health) is Phase 2b — it depends
  on org-specific Collaborative Forecasts / team config.

## How to run
1. Run the ranking engine (defaults to the rep sample book):
   ```bash
   python3 scripts/rank.py
   ```
   Other books and toggles:
   ```bash
   python3 scripts/rank.py --book sample_book_2.json       # a different rep
   python3 scripts/rank.py --book sample_book_leader.json  # a sales leader
   python3 scripts/rank.py --no-ev --no-diversify          # demo the toggles
   ```
   It reads the chosen book + `config/catalog.json`, prints the full ranked
   candidate list (with the value/urgency/severity breakdown), then the **Top 3**
   with a plain-language "why" for each, and finally a `=== JSON ===` block for
   rendering. `preview/cards.html` renders that JSON as the opening message.
2. Present the Top 3 to the rep as **three cards**. For each card show:
   - the headline,
   - the one-line **why** (cite the actual numbers — deal size, days quiet, count),
   - a **button** that continues into the mapped skill chain.
   Render with an interactive widget when one is available (in production, see
   `salesforce-for-sales:using-display-widget`); otherwise present a tight list.
3. **Button behavior (Phase 1):** tapping a button invokes the mapped Salesforce
   for Sales skill against the *sample* record — e.g. `deal-advance-gap` on the
   Acme sample opportunity. Tell the rep that in production this runs on their
   live data and writes results back to Salesforce (preview-then-commit).

## The ranking (summary)
```
score = 0.30 * value  +  0.50 * urgency  +  0.20 * severity
```
Each component is normalized to 0–1. `value` uses **expected value**
(amount x probability) by default, so a likely mid-size deal can outrank a
long-shot bigger one. A play is only eligible if the skill it maps to is
`enabled` in the catalog (no dead-end buttons) and it matches the book's
persona. The Top 3 then de-dupes to one card per play type, **diversifies** so
two cards aren't about the same account, and **guarantees one quick win**.
Full model and rationale: `references/scoring-model.md`. Tune the weights,
thresholds, rules, and skill chains in `config/catalog.json` — no code change needed.

## Files
- `config/catalog.json` — the recommendation catalog: weights, thresholds,
  rules, per-play persona/scope/effort, skill chains, button templates,
  `enabled` flags. **This is the tunable IP.**
- `data/sample_book.json` — a sample rep's opportunities, calls, and leads.
- `data/sample_book_2.json` — a second, differently-shaped rep book.
- `data/sample_book_leader.json` — a sample sales leader's team rollups,
  forecast, key deals, and account health.
- `scripts/rank.py` — the scan + ranking engine (Python stdlib only, no installs).
  `--json` prints just the machine-readable Top 3 (used by the trigger);
  `--book-path <file>` scores a book from any path (used by the live scan).
- `scripts/live_scan.py` — Phase 2 live adapter: maps raw Salesforce SOQL results
  (from the connector's `dispatch_readonly`) into a book the engine consumes.
  Holds the `SOQL_REP` queries. Read-only, stdlib only.
- `scripts/calibrate.py` — weight calibration + robustness harness; also a
  regression check (it grades whatever weights are in the catalog).
- `scripts/session_start.sh` — what the SessionStart hook runs at launch.
- `hooks/hooks.json` — registers the SessionStart trigger.
- `commands/go.md` — the `/first-move:go` manual trigger.
- `preview/cards.html` — the opening message rendered from the engine's JSON.
- `references/scoring-model.md` — how scoring works and why (incl. calibration).
- `references/live-scan.md` — the runtime recipe for the live org scan.
- `.claude-plugin/` — plugin + marketplace manifests for install (see README).

## Honesty / boundaries
- Only surfaces plays whose mapped skill is `enabled` — every button leads somewhere.
- The quality of a live scan is capped by the rep's own Salesforce permissions.
- This layer never forks or re-implements Salesforce for Sales skills; it only
  composes and routes to them.

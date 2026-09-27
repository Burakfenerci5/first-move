---
name: first-move
description: >-
  Opens a seller's Claude session with their top 3 next-best plays from
  Salesforce instead of a blank prompt. Scans what they own, ranks by
  expected-value x urgency x severity, and routes each play to a Salesforce for
  Sales skill. Works for sales reps and sales leaders (managers). Use at the
  start of someone's day, on their first message, or when they ask "what should
  I focus on?" / invoke first-move. Runs live against the seller's connected
  Salesforce and workspace connectors when available (read-only, no writes),
  falling back to bundled sample data only when nothing is connected.
---

# First Move

## What this does
Instead of greeting a seller with a blank box, First Move opens with the
**top 3 things worth their attention right now**, drawn from their own book of
business — each one a real next-best play tied to a Salesforce for Sales skill.
It adapts to who is asking: a **rep** gets deal/call/lead plays; a **sales
leader** gets team-level plays (pipeline coverage, forecast gap, deal reviews).

## When to use
- **Automatically, at session start.** When installed as a plugin, a
  `SessionStart` hook (`hooks/hooks.json` → `scripts/session_start.sh`) fires the
  moment a fresh session launches and instructs Claude to run the Turn-0 scan —
  **live when connectors are available** (see below) — and open with the seller's
  top 3 plays before anything else. The hook is a shell process and cannot reach
  the connectors itself; it triggers the scan and carries the sample fallback,
  while Claude makes the live connector calls inside the session.
- The seller asks "what should I focus on?", "what's on my plate?", or similar.
- The seller runs the `/first-move:go` command, or explicitly invokes `first-move`.

The SessionStart hook is the closest thing to Turn 0 that Claude Code exposes
today: it fires before the seller's first message, so First Move leads rather
than waiting to be asked. True zero-touch (the assistant speaking with no
session action at all) remains a platform capability, not something this skill
forces.

## Data source: live by default, sample as fallback
- **Read-only.** First Move never writes to Salesforce during the scan. Writes
  only happen inside the mapped skill chains a button invokes (Phase 2 action
  layer, which needs the Salesforce for Sales skills via h360).
- **Live org (the default when a Salesforce connector is connected).** Scan the
  seller's real book. The same engine runs against a live book produced by
  `scripts/live_scan.py` from **owner-scoped** SOQL over the connector's
  `dispatch_readonly`. Follow `references/live-scan.md`, then
  `rank.py --book-path <live_book>`. Confirm the connected org is the intended one
  before presenting data as theirs. The rep persona is fully wired from standard
  fields; the live **leader** scan (team rollups, forecast, health) is Phase 2b —
  it depends on org-specific Collaborative Forecasts / team config.
- **Cross-connector signals (Salesforce-anchored).** When Slack / Gmail /
  Calendar are connected, gather read-only signals and fold them into the book as
  a `signals` array (recipe: `references/signals-scan.md`). A signal that names a
  book account **sharpens** that play — it boosts urgency and appends its note to
  the why. A signal with no matching account becomes a **workspace** play that
  only fills a Top-3 slot the Salesforce book leaves open — so a thin or empty
  book (e.g. a non-AE's) still opens with a real first move. Salesforce deals stay
  the spine; signals never displace a live deal play. The engine stays offline —
  the assistant gathers signals at runtime, same as the live scan.
- **Sample data (fallback only).** When **no** Salesforce connector and **no**
  Slack/Gmail/Calendar connector is available, read a bundled book in `data/` so
  the opening still demonstrates the product — and say plainly the plays are
  sample data, with a prompt to connect a source.
- **Empty is not a failure.** An owner-scoped live scan that returns an empty
  book (common for a non-AE) is expected — do **not** widen scope to other
  people's records to manufacture plays. Let signals fill the opening, or say
  there is nothing owner-scoped to surface. Never fabricate plays, and always
  distinguish a blank field from one that was not queried.

## How to run
1. **Get the ranked plays as JSON — live first.**
   - **Live (the default when connected):** if a Salesforce connector with a
     `dispatch_readonly` tool is connected, run the live scan in
     `references/live-scan.md` — discover the API version + running user, confirm
     the org, run the **owner-scoped** `SOQL_REP` queries, assemble the bundle,
     then transform it:
     ```bash
     python3 scripts/live_scan.py --in bundle.json --out live_book.json
     ```
     If Slack / Gmail / Calendar are connected, gather read-only signals
     (`references/signals-scan.md`) and add them to the book's `signals` array —
     today's external meetings are the highest-value, lowest-cost source. Then
     rank the live book:
     ```bash
     python3 scripts/rank.py --json --book-path live_book.json
     ```
   - **Sample (fallback — nothing connected):**
     ```bash
     python3 scripts/rank.py --json
     ```
     Other sample books/toggles for demos:
     ```bash
     python3 scripts/rank.py --book sample_book_2.json       # a different rep
     python3 scripts/rank.py --book sample_book_leader.json  # a sales leader
     python3 scripts/rank.py --no-ev --no-diversify          # demo the toggles
     ```
   The engine reads the book + `config/catalog.json`, prints the full ranked
   candidate list (with the value/urgency/severity breakdown), then the **Top 3**
   with a plain-language "why" for each, and finally a `=== JSON ===` block for
   rendering. `preview/cards.html` renders that JSON as the opening message.
2. **Render the Top 3 as an interactive widget — this is the default, not a
   text list.** Draw one canonical card set so the SessionStart opening and
   `/first-move:go` look identical. Pick the renderer the host offers, in order:
   - **claude.ai / Claude Cowork (primary):** the HTML card widget. Call the
     workspace's HTML widget tool (on claude.ai, the `visualize` connector's
     `show_widget`) with the fragment in `references/opening-widget.md` — a
     responsive grid of color-coded cards (icon + status chip + title + one-line
     **why** verbatim + a `sendPrompt` button that continues into the mapped
     skill chain), a sample/live chip, and a connect card on sample data. This is
     the renderer behind Cowork and the Anthropic directory, so it is the one
     that matters most.
   - **Salesforce-native surface:** the Mosaic `display_widget` (same plays,
     tiles instead of HTML) — see the alternate section of the recipe.
   - **No widget renderer (plain terminal):** a tight numbered list (title, why,
     `[ button ]`).

   Render `top` in the given order; never restate the cards as prose beneath a
   widget that already drew them. Put the sample-vs-live framing sentence in your
   reply text next to the widget, not inside it. Full recipe, canonical fragment,
   and Mosaic envelope: `references/opening-widget.md`.
3. **Button behavior.** Tapping a button continues into the play's mapped
   Salesforce for Sales skill chain (via h360, which needs authorization). On a
   live scan the button acts on the real record; on the sample fallback it
   demonstrates the chain on the sample record (e.g. `deal-advance-gap` on the
   Acme sample opportunity). Either way the action layer is preview-then-commit —
   the seller stays in the loop before any writeback to Salesforce.

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
- `references/opening-widget.md` — the opening-render recipe: the canonical HTML
  card fragment (claude.ai / Cowork, primary), the Mosaic `display_widget`
  envelope (Salesforce surfaces), the engine-JSON → card mapping, sample-vs-live
  framing, signals rendering, and the text fallback.
- `references/signals-scan.md` — the runtime recipe for gathering cross-connector
  signals (Calendar / Gmail / Slack, read-only) and folding them into the book.
- `.claude-plugin/` — plugin + marketplace manifests for install (see README).

## Honesty / boundaries
- Only surfaces plays whose mapped skill is `enabled` — every button leads somewhere.
- The quality of a live scan is capped by the rep's own Salesforce permissions.
- This layer never forks or re-implements Salesforce for Sales skills; it only
  composes and routes to them.

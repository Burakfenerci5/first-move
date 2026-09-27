# First Move

> The AI CRO makes the first move. Open Claude and it already leads — your top 3
> next-best plays, drawn from live revenue context and routed into Salesforce in
> Claude's prebuilt sales skills. No blank prompt. No guessing. Just the next best move.

Claudeforce put 37 prebuilt sales skills inside Claude — **Salesforce in Claude**,
the seller's AI CRO. But every session still opens to a blank prompt, leaving the
seller to decide what to ask first. First Move takes **Turn 0**: it scans the
seller's book, ranks the highest-value plays, and opens with the top 3 — each
routed into one of those prebuilt skills. It's a thin **composition layer**; it
never forks or re-implements the skills — it just decides which move to make first.

## Status: Phase 1 — the brain (sample data, read-only)

This phase proves the hardest, most defensible part: **which three plays, and
why.** It runs entirely on bundled sample data with no Salesforce connection and
makes no writes. It scores on **expected value** (amount × probability) with
**robustness-calibrated weights** (`scripts/calibrate.py`), works for both
**rep and leader** personas, de-dupes and diversifies the Top 3, and guarantees
a quick win.

```bash
python3 scripts/rank.py                         # default rep book
python3 scripts/rank.py --book sample_book_2.json       # a different rep
python3 scripts/rank.py --book sample_book_leader.json  # a sales leader
python3 scripts/rank.py --no-ev --no-diversify          # demo the toggles
python3 scripts/calibrate.py                            # calibrate/QA the weights
```

Each run prints the full ranked candidate list, the Top 3 with a plain-language
"why" for each, and a JSON block. Open `preview/cards.html` in a browser to see
that JSON rendered as the opening message (with a switcher across all three
sample books).

## Layout

```
first-move/                          # plugin root (and a single-plugin marketplace)
├── .claude-plugin/
│   ├── plugin.json                  # plugin manifest
│   └── marketplace.json             # marketplace listing (for easy install)
├── SKILL.md                         # how Claude runs the skill
├── README.md                        # this file
├── config/
│   └── catalog.json                 # the tunable IP: weights, thresholds, rules, skill chains
├── data/
│   ├── sample_book.json             # sample rep book
│   ├── sample_book_2.json           # a second, differently-shaped rep book
│   └── sample_book_leader.json      # sample sales-leader book (team rollups, forecast)
├── commands/
│   └── go.md                        # /first-move:go — manual one-tap trigger
├── hooks/
│   └── hooks.json                   # SessionStart hook — fires First Move on launch
├── scripts/
│   ├── rank.py                      # the scan + ranking engine (stdlib only)
│   ├── live_scan.py                 # Phase 2 live adapter: SOQL results -> book
│   ├── calibrate.py                 # weight calibration + robustness harness
│   └── session_start.sh             # what the SessionStart hook runs (Turn-0 scan)
├── preview/
│   └── cards.html                   # the opening message, rendered from rank.py's JSON
├── tests/
│   └── fixtures/
│       └── live_bundle_rep.json     # raw-SOQL fixture; proves live == sample Top-3
└── references/
    ├── scoring-model.md             # how the ranking works and why
    └── live-scan.md                 # runtime recipe for the live org scan
```

## Install (Phase 4 groundwork)

First Move is packaged as a Claude plugin distributed through a one-plugin
marketplace, so it installs in two commands. Push this folder to a repo (e.g.
`your-org/first-move`), then:

```
/plugin marketplace add your-org/first-move
/plugin install first-move@first-move-marketplace
```

Claude Code reads `.claude-plugin/marketplace.json` from the repo, which points
at the `first-move` plugin (`.claude-plugin/plugin.json`) at the repo root. The
skill (`SKILL.md`) is discovered via the manifest's `"skills": ["."]`. Updating
the repo updates the skill for everyone who installed it.

## Roadmap

- **Phase 0 — Foundations:** authorize the per-user Salesforce connector. *(pending — needs interactive OAuth)*
- **Phase 1 — The brain — done:** scan + rank + explain on sample data, with
  expected-value scoring, robustness-calibrated weights, rep + leader personas,
  and diversification.
- **Phase 2 — The hands:**
  - *Read half — done:* the live-scan adapter (`scripts/live_scan.py`) runs the
    same engine against a live org via the connector's `dispatch_readonly`.
    Verified to reproduce the sample Top-3 exactly (`tests/fixtures/`,
    `references/live-scan.md`). Rep persona wired; leader is Phase 2b.
  - *Write half:* wire buttons to real skill chains + preview-then-commit
    writeback. *(needs the Salesforce for Sales skills via h360)*
- **Phase 3 — The first move — done:** rendered cards (`preview/`) + triggers —
  a `SessionStart` hook that fires the scan on launch and injects the top 3, and
  a `/first-move:go` command for on-demand use.
- **Phase 4 — Easy install:** package as a plugin others add once; self-updates as new skills ship. *(manifests scaffolded; see Install)*
- **North star:** true zero-touch Turn 0, once the platform exposes an opening hook.

## Principles

- Every button leads to an enabled skill — no dead ends.
- Every recommendation shows its reasoning — no black box.
- Every action (from Phase 2) writes back to Salesforce, within the user's own permissions.

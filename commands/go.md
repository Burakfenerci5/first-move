---
description: Show my top 3 next-best Salesforce plays right now (First Move)
---

Invoke the `first-move` skill now to present the seller's **top 3 next-best
plays**, ranked from their book of business.

Steps:
1. Get the ranked plays as JSON.
   - **Live org (preferred when connected):** if a Salesforce connector with a
     `dispatch_readonly` tool is connected, run the live scan in
     `references/live-scan.md` (discover version + user, run the `SOQL_REP`
     queries, assemble a bundle, then
     `live_scan.py --in bundle.json --out live_book.json` and
     `rank.py --json --book-path live_book.json`). Confirm the connected org is
     the intended one before presenting.
   - **Sample data (fallback):** no connector →
     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rank.py" --json
     ```
     To score a specific sample book (rep vs. leader), add
     `--book sample_book_2.json` or `--book sample_book_leader.json`.
2. Present the `top` array as three cards — headline, the one-line **why**
   (quote it verbatim; it cites the real numbers), and an action button using
   the `button` text. Use a display widget if one is available; otherwise a
   tight numbered list.
3. Stop at three and let the seller pick one. Tapping a button continues into
   that play's mapped Salesforce for Sales skill chain.

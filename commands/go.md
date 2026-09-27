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
2. Render the `top` array as an **interactive widget** (the default), using the
   canonical template in `references/opening-widget.md` so this looks identical
   to the SessionStart opening. Pick the renderer the host offers:
   - **claude.ai / Cowork (primary):** the HTML card widget — call the workspace
     HTML widget tool (on claude.ai, `visualize`'s `show_widget`) with the
     canonical fragment: a responsive grid of color-coded cards (icon + status
     chip + `title` + `why` verbatim + a `sendPrompt` button into the mapped
     skill chain), a sample/live chip, and a connect card on sample data.
   - **Salesforce-native surface:** the Mosaic `display_widget` (one
     `tile/callout` per play) — see the recipe's alternate section.
   - **No widget renderer:** a tight numbered list (headline, `why` verbatim,
     `[ button ]`).
   Keep the sample-vs-live framing in your reply text, not inside the widget.
3. Stop at three and let the seller pick one. Tapping a button continues into
   that play's mapped Salesforce for Sales skill chain.

#!/usr/bin/env bash
# First Move — SessionStart hook (Phase 3 trigger).
#
# This is what makes First Move take over Turn 0. When a fresh session starts,
# Claude Code runs this hook BEFORE the seller types anything. It runs the
# Phase-1 ranking engine, then injects the seller's top 3 next-best plays into
# the session as context — so Claude can open with those three cards instead of
# a blank prompt box.
#
# Phase 1: scans the bundled sample book. Phase 2: the same engine runs against
# the seller's live Salesforce book (only the data source changes).
#
# Output contract (Claude Code SessionStart hook): print a single JSON object on
# stdout with hookSpecificOutput.additionalContext; exit 0. On any failure we
# still emit valid JSON with a graceful fallback so a broken scan never blocks
# the session.
set -uo pipefail

# CLAUDE_PLUGIN_ROOT is set when running as an installed plugin; fall back to
# the repo root (this script's parent dir) when run directly for testing.
ROOT="${CLAUDE_PLUGIN_ROOT:-"$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"}"

PLAYS="$(python3 "$ROOT/scripts/rank.py" --json 2>/dev/null || true)"

if [ -z "$PLAYS" ]; then
  CONTEXT="First Move is installed for this seller. At the start of this session, offer to run the first-move skill (or /first-move:go) to show their top 3 next-best plays from Salesforce."
else
  CONTEXT="$(printf '%s' \
"First Move ran a Turn-0 scan of the seller's book of business (Phase 1: bundled sample data; Phase 2 runs this live against Salesforce). Their top 3 next-best plays are ready below as JSON — do NOT recompute them.

Open this session by rendering these three as an interactive widget (the default, not a text list), using the canonical template in references/opening-widget.md. Pick the renderer the host offers: on claude.ai / Claude Cowork (primary) call the HTML widget tool (the visualize connector's show_widget) with the canonical card fragment — a responsive grid of color-coded cards, each with an icon, a status chip, the title, the why exactly as given, and a sendPrompt button that continues into the mapped skill chain, plus a sample/live chip and a connect card on sample data; on a Salesforce-native surface use the Mosaic display_widget instead; with no widget renderer, fall back to a tight numbered list (title, why verbatim, [ button ]). Keep the sample-vs-live framing in your reply text, not inside the widget. Keep it to these three, then let the seller pick one.

TOP_3_PLAYS_JSON:
${PLAYS}")"
fi

# Serialize safely (handles the embedded JSON + newlines) and emit.
python3 - "$CONTEXT" <<'PY'
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": sys.argv[1],
    }
}))
PY

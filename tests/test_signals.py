#!/usr/bin/env python3
"""Regression test for the cross-connector signals layer (Salesforce-anchored).

Runs `rank.py --json` against the two signals sample books and asserts the two
guaranteed behaviors:

  1. Enrichment — a signal that names a book account boosts + annotates that
     Salesforce play, and a signal about a non-book company never displaces a
     live deal play when the Top 3 is already full.
  2. Thin-pipeline fill — when the Salesforce book leaves Top-3 slots open,
     unmatched signals originate `workspace` plays to fill them, ordered by
     recency (a meeting today outranks an older email/Slack ping).

Stdlib only. Run: python3 tests/test_signals.py
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANK = os.path.join(ROOT, "scripts", "rank.py")


def run(book):
    out = subprocess.check_output(
        [sys.executable, RANK, "--json", "--book", book], cwd=ROOT)
    return json.loads(out)


def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        sys.exit(1)
    print("ok:", msg)


def test_enrichment():
    top = run("sample_book_signals.json")["top"]
    check(len(top) == 3, "enrichment: exactly 3 plays")

    acme = top[0]
    check(acme["origin"] == "salesforce",
          "enrichment: top play stays a Salesforce play")
    check("Acme" in acme["title"], "enrichment: the boosted play is Acme's")
    check(acme.get("signal", {}).get("source") == "calendar",
          "enrichment: the calendar signal is attached to the play")
    check("contract review" in acme["why"],
          "enrichment: the signal note is appended to the why")

    # The Stark Industries Slack signal matches no book account and must NOT
    # push out a live deal play when the Top 3 is already full.
    check(all(p["origin"] == "salesforce" for p in top),
          "enrichment: no workspace play displaces a live deal in a full Top 3")


def test_thin_fill():
    top = run("sample_book_thin.json")["top"]
    check(len(top) >= 1, "thin: at least one play surfaced")

    ws = [p for p in top if p["origin"] == "workspace"]
    check(len(ws) >= 1, "thin: workspace plays fill the empty pipeline")

    # A meeting flagged today has max urgency, so it leads.
    check(top[0]["origin"] == "workspace" and top[0]["key"] == "meeting_external",
          "thin: today's meeting is the first move")

    # Every workspace play still routes to an enabled skill chain (no dead ends).
    check(all(p["skill_chain"] for p in ws),
          "thin: every workspace play maps to a skill chain")


if __name__ == "__main__":
    test_enrichment()
    test_thin_fill()
    print("\nAll signals tests passed.")

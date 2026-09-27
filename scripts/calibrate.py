#!/usr/bin/env python3
"""
First Move — weight calibration harness.

We do NOT have labeled closed-won outcomes yet, so this is not a supervised fit
of the weights. Pretending otherwise would be dishonest. Instead it calibrates
the score weights two defensible ways and lets the evidence decide whether the
current 0.40 / 0.35 / 0.25 split is worth changing.

  1. Sensitivity map. Sweep the whole weight simplex (every value/urgency/
     severity split that sums to 1.0, in 0.05 steps) and, per sample book,
     report how stable the #1 pick is. A pick that wins across most of the
     simplex is robust; one that wins in a thin sliver is a knife-edge.

  2. Constraint satisfaction + robustness. A short list of HIGH-confidence
     expert judgments about the sample books ("a $95K deal at 90% going cold
     should outrank generic pipeline hygiene") are encoded as pairwise
     ordering constraints. We find the region of the simplex that satisfies
     ALL of them, check whether today's weights sit inside it, and pick the
     weight that maximizes the *minimum* margin — the point farthest from any
     flip boundary, i.e. the most robust choice.

Deliberately excluded from the constraints: the genuinely debatable calls
(e.g. "should a quiet high-EV deal outrank a call happening today?"). Those are
exactly what weights are supposed to adjudicate, so we let the sensitivity map
show where they flip instead of hard-coding an answer.

Run:  python3 scripts/calibrate.py

Pure standard library + the sibling rank module. No installs, no network.
"""

import os

import rank  # sibling module in scripts/

STEP = 0.05

# Sample books to evaluate, with a short label and (optional) persona override.
BOOKS = [
    ("Jordan (rep)", "sample_book.json", None),
    ("Priya (rep)", "sample_book_2.json", None),
    ("Morgan (leader)", "sample_book_leader.json", None),
]

# High-confidence expert judgments, as pairwise "winner should outrank loser"
# constraints scoped to a book. Kept intentionally to the calls a sales pro
# would make the same way every time — not the debatable ones.
CONSTRAINTS = [
    ("Jordan (rep)", "deal_gone_quiet", "pipeline_hygiene"),   # cold big deal > housekeeping
    ("Jordan (rep)", "deal_gone_quiet", "log_call_outcome"),   # cold big deal > logging admin
    ("Jordan (rep)", "call_today_no_prep", "log_call_outcome"),  # live call today > old call log
    ("Priya (rep)", "untouched_new_leads", "pipeline_hygiene"),  # SLA leads > housekeeping
    ("Priya (rep)", "deal_gone_quiet", "pipeline_hygiene"),      # cold big deal > housekeeping
    ("Morgan (leader)", "team_pipeline_coverage", "rep_needs_coaching"),  # systemic > single-rep
]

def current_weights():
    """The weights actually in the catalog — so re-running always grades
    whatever is live, not a number frozen in this file."""
    w = rank.load_json(rank.CATALOG_PATH)["weights"]
    return (w["value"], w["urgency"], w["severity"])


CURRENT = current_weights()


# --------------------------------------------------------------------------- #
def simplex(step):
    """All (value, urgency, severity) weights >= 0 summing to 1.0, on a grid."""
    n = round(1.0 / step)
    pts = []
    for i in range(n + 1):
        for j in range(n + 1 - i):
            k = n - i - j
            pts.append((round(i * step, 2), round(j * step, 2), round(k * step, 2)))
    return pts


def candidates_for(book_file, persona=None):
    """Run the real detectors, then apply select_top's eligibility filter
    (enabled + persona match) so we score exactly what the engine would."""
    book = rank.load_json(os.path.join(rank.DATA_DIR, book_file))
    catalog = rank.load_json(rank.CATALOG_PATH)
    p = persona or book["rep"].get("persona", "rep")
    cands = rank.detect_leader(book, catalog) if p == "leader" else rank.detect_rep(book, catalog)

    def ok(c):
        rp = catalog["recommendations"][c["key"]].get("persona", "rep")
        return c["enabled"] and rp in (p, "both")

    return [c for c in cands if ok(c)], p


def score(c, w):
    return w[0] * c["value"] + w[1] * c["urgency"] + w[2] * c["severity"]


def best_scores(cands, w):
    """key -> highest score of any candidate of that type, under weight w
    (mirrors select_top keeping one card per type)."""
    best = {}
    for c in cands:
        s = score(c, w)
        if c["key"] not in best or s > best[c["key"]]:
            best[c["key"]] = s
    return best


def top_key(cands, w):
    best = best_scores(cands, w)
    return max(best, key=best.get) if best else None


# --------------------------------------------------------------------------- #
def main():
    grid = simplex(STEP)
    books = {label: candidates_for(f, p) for label, f, p in BOOKS}

    print("=" * 72)
    print("FIRST MOVE — WEIGHT CALIBRATION")
    print("simplex step {}  ·  {} weight vectors  ·  {} sample books".format(
        STEP, len(grid), len(books)))
    print("current weights: value {:.2f}  urgency {:.2f}  severity {:.2f}".format(*CURRENT))
    print("=" * 72)

    # ---- 1) Sensitivity: how stable is each book's #1 pick? ---------------- #
    print("\n1) TOP-PICK STABILITY ACROSS THE WHOLE WEIGHT SIMPLEX")
    print("   (what share of all weight splits give each play the #1 slot)\n")
    for label, (cands, persona) in books.items():
        counts = {}
        for w in grid:
            tk = top_key(cands, w)
            counts[tk] = counts.get(tk, 0) + 1
        cur = top_key(cands, CURRENT)
        print("  {} — {} eligible plays, current #1 = {}".format(label, len(cands), cur))
        for k, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            bar = "#" * round(40 * n / len(grid))
            mark = "  <- current" if k == cur else ""
            print("      {:<26} {:>5.0f}%  {}{}".format(k, 100 * n / len(grid), bar, mark))
        print()

    # ---- 2) Constraint satisfaction + robustness --------------------------- #
    # Pre-resolve which constraints are actually evaluable (both keys present).
    evaluable, skipped = [], []
    for label, win, lose in CONSTRAINTS:
        cands, _ = books[label]
        keys = {c["key"] for c in cands}
        (evaluable if {win, lose} <= keys else skipped).append((label, win, lose))

    def min_margin(w):
        """Smallest (winner - loser) margin over all evaluable constraints at w.
        Negative => at least one expert judgment is violated at this weight."""
        worst = 1.0
        for label, win, lose in evaluable:
            cands, _ = books[label]
            b = best_scores(cands, w)
            worst = min(worst, b[win] - b[lose])
        return worst

    feasible = [w for w in grid if min_margin(w) > 0]
    robust = max(grid, key=min_margin)  # max-min margin: farthest from any boundary

    # Product-sane robust point. Tuning 3 weights to 6 constraints on 3 books
    # overfits, and the unconstrained optimum parks signals at 0. So we bound
    # every signal to a range that keeps it alive on product grounds — value
    # (EV is the differentiator), urgency (this is a "what now?" tool), severity
    # (how bad / how many) — and take the most robust weight inside that box.
    BOX = {"value": (0.30, 0.45), "urgency": (0.35, 0.55), "severity": (0.15, 0.30)}
    in_box = lambda w: (BOX["value"][0] <= w[0] <= BOX["value"][1]
                        and BOX["urgency"][0] <= w[1] <= BOX["urgency"][1]
                        and BOX["severity"][0] <= w[2] <= BOX["severity"][1])
    banded = [w for w in grid if in_box(w)]
    robust_pc = max(banded, key=min_margin)

    print("2) EXPERT-JUDGMENT CONSTRAINTS  ({} evaluable, {} skipped)".format(
        len(evaluable), len(skipped)))
    for label, win, lose in evaluable:
        cands, _ = books[label]
        b = best_scores(cands, CURRENT)
        m = b[win] - b[lose]
        print("   [{}] {} {:>18} > {:<18} margin {:+.3f}".format(
            "ok" if m > 0 else "XX", label.split()[0], win, lose, m))
    for label, win, lose in skipped:
        print("   [--] {} {} > {}  (a key isn't generated by this book — skipped)".format(
            label.split()[0], win, lose))

    print("\n   feasible region: {}/{} weight splits satisfy ALL constraints ({:.0f}%)".format(
        len(feasible), len(grid), 100 * len(feasible) / len(grid)))
    print("   current weights {}:  min margin {:+.3f}  ->  {}".format(
        CURRENT, min_margin(CURRENT),
        "inside feasible region" if min_margin(CURRENT) > 0 else "VIOLATES a constraint"))
    print("   most-robust weights (unconstrained): value {:.2f} urgency {:.2f} severity {:.2f}"
          "  min margin {:+.3f}".format(robust[0], robust[1], robust[2], min_margin(robust)))
    print("      ^ note: drives value->0, discarding expected value. Rejected on product grounds.")
    print("   RECOMMENDED (most robust with every signal kept in a sane range):")
    print("      value {:.2f}  urgency {:.2f}  severity {:.2f}   min margin {:+.3f}   (box: {})".format(
        robust_pc[0], robust_pc[1], robust_pc[2], min_margin(robust_pc),
        " ".join("{} {:.2f}-{:.2f}".format(k, lo, hi) for k, (lo, hi) in BOX.items())))

    # The one genuinely weight-sensitive call: the leader's #1. Show its margin
    # at the current weights and where the constrained-robust weights land it.
    lcands, _ = books["Morgan (leader)"]
    for wlabel, w in (("current", CURRENT), ("constrained-robust", robust_pc)):
        b = best_scores(lcands, w)
        ranked = sorted(b.items(), key=lambda kv: -kv[1])
        (k1, s1), (k2, s2) = ranked[0], ranked[1]
        print("   leader #1 @ {:<18} {} beats {} by {:+.3f}".format(
            wlabel + ":", k1, k2, s1 - s2))

    print("\n" + "=" * 72)
    print("READING THIS: a play that owns the #1 slot across most of the simplex")
    print("is a robust call the weights barely affect. Where two plays split the")
    print("simplex, the weight is the tie-breaker — that's where tuning matters,")
    print("and where honest expert judgment (or real outcome data) has to decide.")
    print("=" * 72)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
First Move — Phase 1 ranking engine (sample data, read-only).

Reads a book of business (data/*.json) and the recommendation catalog
(config/catalog.json), runs one detector per recommendation type for the
book's persona (rep or leader), scores each candidate on value / urgency /
severity, and prints the ranked list + the Top 3 with a plain-language "why".

value uses EXPECTED value (amount x probability) when rules.use_expected_value
is on, so a likely mid-size deal can outrank a long-shot bigger one.

Pure Python standard library. No installs, no network, no Salesforce writes.

Usage:
  python3 scripts/rank.py                         # default rep book
  python3 scripts/rank.py --book sample_book_2.json
  python3 scripts/rank.py --book sample_book_leader.json
  python3 scripts/rank.py --no-ev --no-diversify  # demo the toggles

The record shapes mirror Salesforce fields, so the same detectors run against
a live SOQL / rollup result set in a later phase — only the data source changes.
"""

import argparse
import json
import os
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")
CATALOG_PATH = os.path.join(BASE, "config", "catalog.json")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def is_open(opp):
    """An opportunity is open unless its stage begins with 'Closed'."""
    return not str(opp.get("stage", "")).lower().startswith("closed")


def money(amount):
    return "${:,.0f}".format(amount)


def urgency_from_days(days_to_deadline, horizon):
    """Closer deadlines score higher. Overdue = maxed out. Floor keeps far-off
    items from going to zero so value/severity can still carry them."""
    if days_to_deadline is None:
        return 0.15
    if days_to_deadline <= 0:
        return 1.0
    return clamp((horizon - days_to_deadline) / horizon, 0.15, 1.0)


def mk(key, catalog, account, value, urgency, severity, fields, why):
    """Assemble a scored candidate from catalog metadata + computed components.
    dkey is the diversification key: account-/rep-scoped cards compete for a
    slot per entity; portfolio-scoped cards never block each other."""
    rec = catalog["recommendations"][key]
    w = catalog["weights"]
    value, urgency, severity = clamp(value), clamp(urgency), clamp(severity)
    score = w["value"] * value + w["urgency"] * urgency + w["severity"] * severity
    scope = rec.get("scope", "account")
    return {
        "key": key,
        "enabled": rec.get("enabled", True),
        "persona": rec.get("persona", "rep"),
        "scope": scope,
        "dkey": None if scope == "portfolio" else account,
        "effort": rec.get("effort", "medium"),
        "account": account,
        "title": rec["title"].format(**fields),
        "button": rec["button"].format(**fields),
        "skill_chain": rec["skill_chain"],
        "value": round(value, 3),
        "urgency": round(urgency, 3),
        "severity": round(severity, 3),
        "score": round(score, 4),
        "why": why,
    }


# --------------------------------------------------------------------------- #
# Rep detectors — each recommendation type surfaces its candidate(s).
# --------------------------------------------------------------------------- #
def detect_rep(book, catalog):
    as_of = parse_date(catalog["as_of"])
    th = catalog["thresholds"]
    horizon = th["urgency_horizon_days"]
    stale_cap = th["stale_cap_days"]
    use_ev = catalog["rules"].get("use_expected_value", True)

    opps = book.get("opportunities", [])
    tasks = book.get("tasks", [])
    leads = book.get("leads", [])
    open_opps = [o for o in opps if is_open(o)]

    def basis(o):
        """Money that drives `value`: expected value (amount x probability)
        when enabled, else raw amount. Missing probability = treat as certain."""
        amt = o.get("amount", 0)
        if use_ev:
            p = o.get("probability")
            return amt * (p / 100.0) if p is not None else amt
        return amt

    portfolio_max = max((basis(o) for o in open_opps), default=1) or 1

    def vnorm(x):
        return clamp(x / portfolio_max)

    def days_since(d):
        return (as_of - d).days if d else None

    def days_until(d):
        return (d - as_of).days if d else None

    cands = []

    # 1) Deal gone quiet — one candidate per quiet open deal; select_top keeps
    #    the best. Close-date urgency (not just staleness) decides the winner.
    for o in open_opps:
        ds = days_since(parse_date(o.get("last_activity_date")))
        if ds is None or ds < th["quiet_min_days"]:
            continue
        dtc = days_until(parse_date(o["close_date"]))
        cands.append(mk(
            "deal_gone_quiet", catalog, o["account"],
            value=vnorm(basis(o)),
            urgency=urgency_from_days(dtc, horizon),
            severity=clamp(ds / stale_cap),
            fields={"account": o["account"]},
            why="{acct} ({amt}) closes in {d} days and has had no activity in {ds} days.".format(
                acct=o["account"], amt=money(o["amount"]), d=dtc, ds=ds),
        ))

    # 2) Call today, no prep — pick the one on the biggest (expected) deal.
    todays = []
    for t in tasks:
        if t.get("type") == "Call" and parse_date(t.get("activity_date")) == as_of \
                and str(t.get("status")) != "Completed":
            opp = next((o for o in opps if o["id"] == t.get("related_opp_id")), None)
            todays.append((t, opp))
    if todays:
        t, opp = max(todays, key=lambda x: basis(x[1]) if x[1] else 0)
        amt = opp["amount"] if opp else 0
        # Tasks carry no time-of-day (only Events do); name the time when we have
        # it, otherwise just say "today" rather than "today at today".
        when = t.get("start_time")
        at = " at %s" % when if when else ""
        cands.append(mk(
            "call_today_no_prep", catalog, t["related_account"],
            value=vnorm(basis(opp)) if opp else 0.3,
            urgency=1.0,
            severity=0.6,
            fields={"account": t["related_account"]},
            why="Call with {acct} today{at} on a {amt} deal — no prep logged yet.".format(
                acct=t["related_account"], at=at, amt=money(amt)),
        ))

    # 3) Pipeline hygiene — open deals missing a next step or past their close date.
    gaps = []
    for o in open_opps:
        dtc = days_until(parse_date(o["close_date"]))
        if not str(o.get("next_step", "")).strip() or (dtc is not None and dtc < 0):
            gaps.append((o, dtc))
    if gaps:
        soonest = min(g[1] for g in gaps if g[1] is not None)
        past = sum(1 for _, dtc in gaps if dtc is not None and dtc < 0)
        cands.append(mk(
            "pipeline_hygiene", catalog, "several accounts",
            value=vnorm(max(basis(o) for o, _ in gaps)),
            urgency=urgency_from_days(soonest, horizon),
            severity=clamp(len(gaps) / th["hygiene_gap_cap"]),
            fields={"count": len(gaps)},
            why="{n} open deals are missing a next step{extra}.".format(
                n=len(gaps), extra=" (one is already past its close date)" if past else ""),
        ))

    # 4) Log call outcome — past calls not yet completed. Housekeeping, moderate urgency.
    unlogged = []
    for t in tasks:
        d = parse_date(t.get("activity_date"))
        if t.get("type") == "Call" and d is not None and d < as_of \
                and str(t.get("status")) != "Completed":
            unlogged.append((t, days_since(d)))
    if unlogged:
        t, ds = min(unlogged, key=lambda x: x[1])  # most recent call = freshest memory
        opp = next((o for o in opps if o["id"] == t.get("related_opp_id")), None)
        cands.append(mk(
            "log_call_outcome", catalog, t["related_account"],
            value=vnorm(basis(opp)) if opp else 0.3,
            urgency=0.6,
            severity=clamp(len(unlogged) / th["unlogged_call_cap"]),
            fields={"count": len(unlogged)},
            why="{n} past calls aren't logged yet — including {acct} {ds} days ago. Capture them while fresh.".format(
                n=len(unlogged), acct=t["related_account"], ds=ds),
        ))

    # 5) Close date slipping — closing very soon but not in a late stage.
    slipping = []
    for o in open_opps:
        dtc = days_until(parse_date(o["close_date"]))
        late = any(k in o["stage"].lower() for k in ("negotiation", "contract", "closed"))
        if dtc is not None and 0 <= dtc <= th["closing_soon_days"] and not late:
            slipping.append((o, dtc))
    if slipping:
        o, dtc = min(slipping, key=lambda x: x[1])
        ds = days_since(parse_date(o.get("last_activity_date"))) or 0
        cands.append(mk(
            "close_date_slipping", catalog, o["account"],
            value=vnorm(basis(o)),
            urgency=urgency_from_days(dtc, horizon),
            severity=clamp(ds / stale_cap),
            fields={"account": o["account"], "days": dtc},
            why="{acct} ({amt}) closes in {d} days but is still in {stage}.".format(
                acct=o["account"], amt=money(o["amount"]), d=dtc, stage=o["stage"]),
        ))

    # 6) Untouched new leads — new, recent, no activity. SLA-driven urgency.
    fresh = []
    for ld in leads:
        age = days_since(parse_date(ld.get("created_date")))
        if str(ld.get("status")) == "New" and age is not None \
                and age <= th["new_lead_max_age_days"] and not ld.get("last_activity_date"):
            fresh.append(ld)
    if fresh:
        cands.append(mk(
            "untouched_new_leads", catalog, "new leads",
            value=vnorm(th["lead_proxy_value"] * len(fresh)),
            urgency=0.85,
            severity=clamp(len(fresh) / 3),
            fields={"count": len(fresh)},
            why="{n} new leads created this week have had no first touch yet.".format(n=len(fresh)),
        ))

    # 7) Renewal on the horizon.
    renewals = []
    for o in open_opps:
        dtr = days_until(parse_date(o.get("contract_end_date")))
        if dtr is not None and 0 <= dtr <= th["renewal_window_days"]:
            renewals.append((o, dtr))
    if renewals:
        o, dtr = min(renewals, key=lambda x: x[1])
        ds = days_since(parse_date(o.get("last_activity_date"))) or 0
        cands.append(mk(
            "renewal_horizon", catalog, o["account"],
            value=vnorm(basis(o)),
            urgency=urgency_from_days(dtr, horizon),
            severity=clamp(ds / stale_cap),
            fields={"account": o["account"], "days": dtr},
            why="{acct} ({amt}) renews in {d} days and hasn't been touched in {ds} days.".format(
                acct=o["account"], amt=money(o["amount"]), d=dtr, ds=ds),
        ))

    return cands


# --------------------------------------------------------------------------- #
# Leader detectors — team rollups, forecast, key deals, account health.
# value is normalized against the quarter's quota (the leader's denominator).
# --------------------------------------------------------------------------- #
def detect_leader(book, catalog):
    as_of = parse_date(catalog["as_of"])
    th = catalog["thresholds"]
    horizon = th["urgency_horizon_days"]
    stale_cap = th["stale_cap_days"]

    fc = book.get("forecast", {})
    team = book.get("team", [])
    quota = fc.get("quota") or sum(m.get("quota", 0) for m in team) or 1

    def vq(x):
        return clamp(x / quota)

    def days_until(d):
        return (parse_date(d) - as_of).days if d else None

    cands = []

    # 1) Forecast gap — commit short of quota with the quarter clock running.
    if fc:
        gap = max(fc.get("quota", 0) - fc.get("commit", 0), 0)
        if gap > 0:
            days_left = fc.get("days_left")
            pct = round(gap / fc["quota"] * 100)
            cands.append(mk(
                "forecast_gap", catalog, "the whole team",
                value=vq(gap),
                urgency=urgency_from_days(days_left, horizon),
                severity=clamp(gap / fc["quota"]),
                fields={"pct": pct},
                why="Commit is {c} against a {q} quota — {g} ({pct}%) uncovered with {d} days left in {p}.".format(
                    c=money(fc["commit"]), q=money(fc["quota"]), g=money(gap), pct=pct,
                    d=days_left, p=fc.get("period", "the quarter")),
            ))

    # 2) Team pipeline coverage — reps under the healthy coverage multiple.
    target = th["coverage_target_multiple"]
    below = []
    for m in team:
        remaining = max(m.get("quota", 0) - m.get("closed", 0), 1)
        cov = m.get("pipeline", 0) / remaining
        if cov < target:
            below.append((m, cov, remaining))
    if below:
        worst = min(below, key=lambda x: x[1])
        cands.append(mk(
            "team_pipeline_coverage", catalog, "the whole team",
            value=vq(sum(r for _, _, r in below)),
            urgency=urgency_from_days(fc.get("days_left"), horizon),
            severity=clamp(len(below) / max(len(team), 1)),
            fields={"count": len(below)},
            why="{n} of {t} reps are under {x}x coverage — {w} is lowest at {c}x.".format(
                n=len(below), t=len(team), x=("%g" % target), w=worst[0]["name"], c=round(worst[1], 1)),
        ))

    # 3) Deal needs review — biggest team deal stuck (no close plan or gone quiet).
    stuck = []
    for d in book.get("key_deals", []):
        la = parse_date(d.get("last_activity_date"))
        ds = (as_of - la).days if la else None
        if (ds is not None and ds >= th["quiet_min_days"]) or not d.get("has_close_plan", False):
            stuck.append((d, ds or 0))
    if stuck:
        d, ds = max(stuck, key=lambda x: x[0]["amount"])
        no_plan = not d.get("has_close_plan", False)
        reason = "no close plan" if no_plan else "no activity in %d days" % ds
        cands.append(mk(
            "deal_needs_review", catalog, d["account"],
            value=vq(d["amount"]),
            urgency=urgency_from_days(days_until(d["close_date"]), horizon),
            severity=clamp(max(ds / stale_cap, 0.7 if no_plan else 0.0)),
            fields={"account": d["account"]},
            why="{acct} ({amt}, {o}) closes in {dtc} days with {reason}.".format(
                acct=d["account"], amt=money(d["amount"]), o=d["owner"],
                dtc=days_until(d["close_date"]), reason=reason),
        ))

    # 4) Rep needs coaching — lowest-activity rep, well under the team target.
    act_target = th["coaching_activity_target"]
    if team:
        m = min(team, key=lambda r: r.get("activities_last_7d", 0))
        if m.get("activities_last_7d", 0) < act_target * 0.5:
            remaining = max(m.get("quota", 0) - m.get("closed", 0), 0)
            cands.append(mk(
                "rep_needs_coaching", catalog, m["name"],
                value=vq(remaining),
                urgency=0.5,
                severity=clamp(1 - m.get("activities_last_7d", 0) / act_target),
                fields={"account": m["name"]},
                why="{n} logged {a} activities in 7 days (target {t}) with {r} left to quota.".format(
                    n=m["name"], a=m.get("activities_last_7d", 0), t=act_target, r=money(remaining)),
            ))

    # 5) Account at risk — low health score approaching renewal.
    at_risk = [a for a in book.get("key_accounts", [])
               if a.get("health_score", 100) < th["health_risk_threshold"]]
    if at_risk:
        a = min(at_risk, key=lambda x: x["health_score"])
        cands.append(mk(
            "account_at_risk", catalog, a["name"],
            value=vq(a["arr"]),
            urgency=urgency_from_days(days_until(a["renewal_date"]), horizon),
            severity=clamp((100 - a["health_score"]) / 100),
            fields={"account": a["name"]},
            why="{acct} (health {h}/100, {arr} ARR) renews in {d} days.".format(
                acct=a["name"], h=a["health_score"], arr=money(a["arr"]),
                d=days_until(a["renewal_date"])),
        ))

    return cands


# --------------------------------------------------------------------------- #
# Rank + select
# --------------------------------------------------------------------------- #
def select_top(candidates, catalog, persona):
    rules = catalog.get("rules", {})
    top_n = rules.get("top_n", 3)
    use_div = rules.get("diversify", False)

    def persona_ok(c):
        p = catalog["recommendations"][c["key"]].get("persona", "rep")
        return p in (persona, "both")

    eligible = [c for c in candidates if c["enabled"] and persona_ok(c)]

    # One card per recommendation type: keep the highest-scoring instance.
    best_by_key = {}
    for c in eligible:
        if c["key"] not in best_by_key or c["score"] > best_by_key[c["key"]]["score"]:
            best_by_key[c["key"]] = c
    ranked = sorted(best_by_key.values(), key=lambda c: c["score"], reverse=True)

    # Fill the Top N, optionally avoiding two cards about the same entity.
    top, seen = [], set()
    for c in ranked:
        if len(top) >= top_n:
            break
        if use_div and c["dkey"] is not None and c["dkey"] in seen:
            continue
        top.append(c)
        if c["dkey"] is not None:
            seen.add(c["dkey"])

    # Guarantee at least one quick win (low-effort) in the Top N.
    if rules.get("guarantee_quick_win") and top and not any(c["effort"] == "low" for c in top):
        low = next((c for c in ranked if c["effort"] == "low" and c not in top), None)
        if low:
            top[-1] = low
            top.sort(key=lambda c: c["score"], reverse=True)

    return ranked, top


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="First Move — Phase 1 ranking engine")
    ap.add_argument("--book", default="sample_book.json", help="data/<file> to score")
    ap.add_argument("--book-path", dest="book_path",
                    help="load the book from this exact path (e.g. a live-scan "
                         "book from scripts/live_scan.py), bypassing data/")
    ap.add_argument("--persona", choices=["rep", "leader"], help="override book persona")
    ap.add_argument("--no-ev", action="store_true", help="score on raw amount, not expected value")
    ap.add_argument("--no-diversify", action="store_true", help="allow multiple cards per account")
    ap.add_argument("--json", action="store_true",
                    help="print only the machine-readable JSON (for the SessionStart hook)")
    args = ap.parse_args()

    book = load_json(args.book_path or os.path.join(DATA_DIR, args.book))
    catalog = load_json(CATALOG_PATH)
    if args.no_ev:
        catalog["rules"]["use_expected_value"] = False
    if args.no_diversify:
        catalog["rules"]["diversify"] = False

    rep = book["rep"]
    persona = args.persona or rep.get("persona", "rep")
    candidates = detect_leader(book, catalog) if persona == "leader" else detect_rep(book, catalog)
    ranked, top = select_top(candidates, catalog, persona)

    payload = {"rep": rep, "as_of": catalog["as_of"], "persona": persona, "top": top}
    if args.json:
        print(json.dumps(payload))
        return

    flags = "expected-value {}  ·  diversify {}".format(
        "on" if catalog["rules"].get("use_expected_value") else "off",
        "on" if catalog["rules"].get("diversify") else "off")

    print("=" * 72)
    print("FIRST MOVE  ·  {name}, {role}".format(name=rep["name"], role=rep["role"]))
    print("as of {d}  ·  {persona}  ·  read-only  ·  {flags}".format(
        d=catalog["as_of"], persona=persona, flags=flags))
    print("=" * 72)

    w = catalog["weights"]
    print("\nAll candidates (ranked)  [score = {v:g} value + {u:g} urgency + {s:g} severity]\n".format(
        v=w["value"], u=w["urgency"], s=w["severity"]))
    print("  {:<24} {:>6} {:>6} {:>6} {:>7}  {}".format(
        "type", "value", "urg", "sev", "SCORE", "effort"))
    print("  " + "-" * 66)
    for c in ranked:
        print("  {:<24} {:>6.2f} {:>6.2f} {:>6.2f} {:>7.3f}  {}".format(
            c["key"], c["value"], c["urgency"], c["severity"], c["score"], c["effort"]))

    print("\n" + "-" * 72)
    print("YOUR TOP {}".format(len(top)))
    print("-" * 72)
    for i, c in enumerate(top, 1):
        print("\n{n}. {title}".format(n=i, title=c["title"]))
        print("   why:    {why}".format(why=c["why"]))
        print("   skills: {chain}".format(chain="  ->  ".join(c["skill_chain"])))
        print("   button: [ {b} ]".format(b=c["button"]))

    print("\n=== JSON ===")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

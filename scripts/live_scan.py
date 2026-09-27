#!/usr/bin/env python3
"""
First Move — Phase 2 live-scan adapter (read-only).

Turns a live Salesforce org into the exact "book of business" shape the Phase-1
ranking engine (scripts/rank.py) already consumes — so the brain never changes,
only the data source does.

HOW IT FITS TOGETHER
--------------------
The Salesforce REST calls are made by the assistant through the connected
Salesforce connector's `dispatch_readonly` tool (a GET against the org). This
module is the *pure, offline, testable* half: given the raw JSON those GETs
return, it maps standard Salesforce fields onto the book schema. It performs no
network I/O and imports nothing outside the standard library, so it runs and is
tested without a live org.

Runtime flow (see references/live-scan.md for the full recipe):
  1. Assistant discovers the API version + running user via dispatch_readonly.
  2. Assistant runs the SOQL in SOQL_REP (below), one query per object.
  3. Assistant writes the raw response bodies into one bundle JSON:
        { "rep": {...}, "opportunities": <body>, "tasks": <body>, "leads": <body> }
  4. python3 scripts/live_scan.py --in bundle.json --out live_book.json
  5. python3 scripts/rank.py --book-path live_book.json
     -> identical Top-3 selection logic, now on live data.

SCOPE
-----
- Read-only. This adapter never writes to Salesforce.
- Rep persona is fully wired from standard fields. The leader persona depends on
  Collaborative Forecasts + a team definition + (often) custom health fields,
  which are org-specific; its live wiring is Phase 2b and intentionally not
  faked here. detect_leader still runs against a hand-supplied leader book.
"""

import argparse
import json
import sys

# --------------------------------------------------------------------------- #
# SOQL the assistant runs via dispatch_readonly (GET /services/data/vXX/query).
# Standard fields only, so these compile in any org (incl. a fresh trailhead
# org). '{user_id}' is the running user's 18-char Id (from /services/oauth2/
# userinfo). Every query is owner-scoped so First Move shows *my* book.
# --------------------------------------------------------------------------- #
SOQL_REP = {
    "opportunities": (
        "SELECT Id, Name, Amount, Probability, StageName, CloseDate, "
        "LastActivityDate, NextStep, Type, Account.Name, "
        "(SELECT Id FROM OpportunityContactRoles) "
        "FROM Opportunity "
        "WHERE IsClosed = false AND OwnerId = '{user_id}' "
        "ORDER BY CloseDate ASC LIMIT 200"
    ),
    # Open call tasks (any Status that isn't a closed/Completed one). Covers both
    # "call today, no prep" and "log the outcome of past calls" — the detectors
    # split them by date. Type='Call' OR TaskSubtype='Call' handles orgs that use
    # either convention.
    "tasks": (
        "SELECT Id, Subject, Type, TaskSubtype, ActivityDate, Status, "
        "WhatId, What.Name "
        "FROM Task "
        "WHERE OwnerId = '{user_id}' AND IsClosed = false "
        "AND ActivityDate != null AND (Type = 'Call' OR TaskSubtype = 'Call') "
        "ORDER BY ActivityDate ASC LIMIT 200"
    ),
    "leads": (
        "SELECT Id, Name, Company, Status, CreatedDate, LastActivityDate "
        "FROM Lead "
        "WHERE OwnerId = '{user_id}' AND IsConverted = false "
        "ORDER BY CreatedDate DESC LIMIT 200"
    ),
}

# Optional: if the org models a renewal/contract-end date, name the field(s)
# here and the renewal_horizon detector lights up. Standard Opportunity has no
# such field, so this stays empty until an org maps one. Add the field to the
# opportunities SELECT above too when you enable it.
CONTRACT_END_FIELDS = ("ContractEndDate__c", "Contract_End_Date__c", "Renewal_Date__c")


# --------------------------------------------------------------------------- #
# Transform helpers
# --------------------------------------------------------------------------- #
def _date(value):
    """Normalize a Salesforce Date ('2026-09-30') or DateTime
    ('2026-09-30T14:00:00.000+0000') to 'YYYY-MM-DD'; pass through None/empty."""
    if not value:
        return None
    return str(value)[:10]


def _records(query_body):
    """Pull the .records list out of a REST query response body (or []).
    Accepts either the raw body dict or an already-unwrapped list."""
    if query_body is None:
        return []
    if isinstance(query_body, list):
        return query_body
    return query_body.get("records", []) or []


def _subquery_count(record, relationship):
    """Count rows in a child-relationship subquery (e.g. OpportunityContactRoles).
    Salesforce returns {'totalSize': N, 'records': [...]} or null."""
    sub = record.get(relationship)
    if isinstance(sub, dict):
        return sub.get("totalSize", len(sub.get("records", []) or []))
    return 0


def _account_name(record):
    acct = record.get("Account")
    if isinstance(acct, dict):
        return acct.get("Name")
    # Some queries flatten it; fall back gracefully.
    return record.get("Account.Name") or record.get("AccountName")


def _what_object(what_id):
    """Infer the polymorphic What object type from the Id key prefix, so we don't
    need TYPEOF in the SOQL. 006=Opportunity, 001=Account."""
    if not what_id or len(what_id) < 3:
        return None
    return {"006": "Opportunity", "001": "Account"}.get(what_id[:3])


# --------------------------------------------------------------------------- #
# Bundle -> book
# --------------------------------------------------------------------------- #
def build_book(bundle):
    """Map a bundle of raw dispatch_readonly response bodies onto the rep book
    schema that rank.py consumes. Pure and deterministic."""
    rep_in = bundle.get("rep") or {}
    rep = {
        "name": rep_in.get("name") or "(me)",
        "role": rep_in.get("role") or "Account Executive",
        "persona": rep_in.get("persona") or "rep",
        "user_id": rep_in.get("user_id") or "",
    }

    # --- Opportunities ---
    opportunities = []
    account_by_opp_id = {}
    for r in _records(bundle.get("opportunities")):
        opp_id = r.get("Id")
        account = _account_name(r) or "(no account)"
        opp = {
            "id": opp_id,
            "name": r.get("Name"),
            "account": account,
            "amount": r.get("Amount") or 0,
            "probability": r.get("Probability"),  # keep None/0 distinct for EV
            "stage": r.get("StageName") or "",
            "close_date": _date(r.get("CloseDate")),
            "last_activity_date": _date(r.get("LastActivityDate")),
            "next_step": r.get("NextStep") or "",
            "type": r.get("Type") or "",
            "contact_count": _subquery_count(r, "OpportunityContactRoles"),
        }
        for f in CONTRACT_END_FIELDS:
            if r.get(f):
                opp["contract_end_date"] = _date(r.get(f))
                break
        opportunities.append(opp)
        account_by_opp_id[opp_id] = account

    # --- Tasks (calls) ---
    tasks = []
    for r in _records(bundle.get("tasks")):
        what_id = r.get("WhatId")
        what = r.get("What") if isinstance(r.get("What"), dict) else {}
        obj = _what_object(what_id)
        related_opp_id = what_id if obj == "Opportunity" else None
        if related_opp_id and related_opp_id in account_by_opp_id:
            related_account = account_by_opp_id[related_opp_id]
        else:
            related_account = what.get("Name") or "(no account)"
        task_type = r.get("Type") or ("Call" if r.get("TaskSubtype") == "Call" else "")
        tasks.append({
            "id": r.get("Id"),
            "subject": r.get("Subject") or "",
            "type": task_type,
            "activity_date": _date(r.get("ActivityDate")),
            "status": r.get("Status") or "",
            "related_account": related_account,
            "related_opp_id": related_opp_id,
        })

    # --- Leads ---
    leads = []
    for r in _records(bundle.get("leads")):
        leads.append({
            "id": r.get("Id"),
            "name": r.get("Name"),
            "company": r.get("Company") or "",
            "status": r.get("Status") or "",
            "created_date": _date(r.get("CreatedDate")),
            "last_activity_date": _date(r.get("LastActivityDate")),
        })

    return {
        "_source": "live",
        "rep": rep,
        "opportunities": opportunities,
        "tasks": tasks,
        "leads": leads,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(
        description="Transform a bundle of raw Salesforce query responses into a "
                    "First Move book (read-only, stdlib only).")
    ap.add_argument("--in", dest="infile",
                    help="bundle JSON path (default: read from stdin)")
    ap.add_argument("--out", dest="outfile",
                    help="write the book here (default: write to stdout)")
    args = ap.parse_args()

    raw = open(args.infile, encoding="utf-8").read() if args.infile else sys.stdin.read()
    bundle = json.loads(raw)
    book = build_book(bundle)
    out = json.dumps(book, indent=2)

    if args.outfile:
        with open(args.outfile, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    else:
        print(out)


if __name__ == "__main__":
    main()

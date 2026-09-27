# Live scan (Phase 2 — read half)

How First Move runs its Turn-0 scan against a **live Salesforce org** instead of
the bundled sample book. The ranking brain (`scripts/rank.py`) is unchanged; only
the data source swaps. Reads only — no writes here (writeback is the button/skill
layer, which needs the Salesforce for Sales skills via h360).

## Prerequisite

A Salesforce connector authorized against the target org is connected in the
session (check `session_connectors_status`; look for a `connected` Salesforce
connector with a `dispatch_readonly` tool). Any Salesforce REST connector works
for the read — h360 is only required for the action buttons.

> The connector is bound to whichever org the user signed into. Confirm the org
> before presenting data as "theirs" (Step 1). Never assume the connected org is
> the intended one — e.g. an internal dogfood connector may point at a corporate
> production org, not the user's test org.

## Recipe

All GETs go through the connected Salesforce connector's `dispatch_readonly`
(method `GET`, `url` = a relative path, SOQL passed via `queryParams.q`).

**1. Discover the API version + running user (and confirm the org).**
- `GET /services/data/` → take the highest `vNN.0`; use it in the paths below.
- `GET /services/oauth2/userinfo` → `user_id`, `name`; and `organization_id` /
  the instance host to confirm this is the intended org.

**2. Run the rep scan** — one GET per object, SOQL from `SOQL_REP` in
`scripts/live_scan.py`, substituting `{user_id}`:
- `GET /services/data/vNN.0/query` with `q` = `SOQL_REP["opportunities"]`
- `GET /services/data/vNN.0/query` with `q` = `SOQL_REP["tasks"]`
- `GET /services/data/vNN.0/query` with `q` = `SOQL_REP["leads"]`

If a result is paged (`done: false`), follow `nextRecordsUrl` and concatenate
`records`. (The `LIMIT 200` cap makes this rare for a single rep's open book.)

**3. Assemble the bundle** — write the three raw response **bodies** plus the
rep identity into one JSON file:
```json
{
  "rep": { "name": "<from userinfo>", "role": "Account Executive", "persona": "rep", "user_id": "<from userinfo>" },
  "opportunities": { "records": [ ... ] },
  "tasks":         { "records": [ ... ] },
  "leads":         { "records": [ ... ] }
}
```

**4. Transform → book, then rank:**
```bash
python3 scripts/live_scan.py --in bundle.json --out live_book.json
python3 scripts/rank.py --json --book-path live_book.json
```

**5. Present** the `top` array exactly as in Phase 1 — three cards (headline,
verbatim why, action button). Same rendering, same button→skill-chain mapping.

## Field mapping (rep)

| Book field | Salesforce source |
|---|---|
| `opportunities[].account` | `Opportunity.Account.Name` |
| `opportunities[].amount` / `probability` | `Amount` / `Probability` |
| `opportunities[].stage` | `StageName` (open = `IsClosed = false`) |
| `opportunities[].close_date` / `last_activity_date` | `CloseDate` / `LastActivityDate` |
| `opportunities[].next_step` / `type` | `NextStep` / `Type` |
| `opportunities[].contact_count` | `OpportunityContactRoles` subquery `totalSize` |
| `opportunities[].contract_end_date` *(optional)* | a contract/renewal date field, if the org maps one (see `CONTRACT_END_FIELDS`) |
| `tasks[]` (calls) | `Task` where `Type='Call' OR TaskSubtype='Call'`, open; `related_opp_id` inferred from the `WhatId` `006` prefix |
| `leads[]` | `Lead` where `IsConverted = false` |

## Known gaps / honest limits

- **Call time-of-day.** Tasks have no time field, so "call today" reads "today"
  rather than "today at 2pm". Use Events (`StartDateTime`) if the org logs calls
  as Events and time matters.
- **Renewals.** Standard `Opportunity` has no contract-end date. `renewal_horizon`
  only fires when an org maps one via `CONTRACT_END_FIELDS` (add it to the
  opportunities SELECT too).
- **Leader persona is Phase 2b.** Team coverage, forecast gap, deal reviews, and
  account health depend on Collaborative Forecasts, a team definition, and
  (often) custom health fields — all org-specific. `detect_leader` still runs;
  its live feed isn't wired here to avoid faking org structure.
- Scan quality is capped by the running user's own Salesforce permissions.

## Test

`tests/fixtures/live_bundle_rep.json` mirrors real `dispatch_readonly` output and
reproduces `data/sample_book.json`. Transforming it and ranking yields the same
Top-3 (identical scores and why-text) as ranking the sample book directly — the
regression that proves the adapter changes nothing but the data source.

# Opening widget — how First Move renders the Top 3

First Move's opening is a **rich interactive widget**, not a text list. Three
color-coded cards, one per play, each with a button that launches the mapped
Salesforce for Sales skill chain. This is what makes Turn 0 feel like the sales
skills themselves rather than a plain reply.

**Pick the renderer the host offers, in this order:**

1. **claude.ai / Claude Cowork → HTML card widget** (the primary path). Render
   with the workspace's HTML widget tool — on claude.ai that is the `visualize`
   connector's **`show_widget`**. This is the renderer behind the Cowork
   experience *and* the Anthropic directory listing, so it is the one that
   matters most. Details below.
2. **Salesforce-native surface (Agentforce / an MCP-Apps host) → Mosaic tiles.**
   Render with the Salesforce connector's `display_widget`. See
   "Alternate renderer" at the bottom.
3. **No widget renderer (e.g. a plain terminal) → tight numbered text list.**
   See "Fallback" at the bottom.

Use the same input for all three; only the drawing differs.

## Input

The plays come from `scripts/rank.py --json` (the SessionStart hook already runs
it; `/first-move:go` runs it too). Shape:

```json
{
  "rep":  { "name": "Jordan Rivera", "role": "Account Executive", "persona": "rep" },
  "as_of": "2026-09-26",
  "persona": "rep",
  "top": [
    {
      "key": "deal_gone_quiet",
      "title": "Acme Corp's deal has gone quiet",
      "why": "Acme Corp ($95,000) closes in 4 days and has had no activity in 12 days.",
      "button": "Help me re-engage Acme Corp",
      "skill_chain": ["deal-signals", "deal-advance-gap", "draft-outreach"],
      "variant": "error",
      "eyebrow": "Re-engage",
      "effort": "medium",
      "scope": "account",
      "origin": "salesforce",
      "signal": null
    }
  ]
}
```

Do **not** recompute or reorder the plays — render `top` in the order given.
`origin` is `"salesforce"` or `"workspace"`; `signal` is `null` or
`{ "source": "slack|email|calendar", "who": "...", "when": "2h ago", "link": "..." }`.

---

## Path 1 — HTML card widget (claude.ai / Cowork) — PRIMARY

Render one canonical card set so `/first-move:go` and the SessionStart opening
produce **identical** output. Call the host's HTML widget tool (on claude.ai,
`show_widget`) with:

- `title`: `first_move_top3_plays` (snake_case; also the download filename).
- `widget_code`: the HTML fragment below.

Before the **first** `show_widget` call in a session, call the widget
connector's `read_me` once (module `mockup`) — the platform requires it and it
returns the live CSS-variable set.

### Rules (from the widget platform)

- **The fragment is visual only.** No `<!DOCTYPE>`, `<html>`, `<head>`, or
  `<body>`. No explanatory paragraphs or headings inside the widget — the
  sample-vs-live framing sentence goes in your **reply text**, next to the
  widget, not in it.
- **Colors only via CSS variables** — never hard-coded hex. Use `--surface-1/2`,
  `--border`, `--border-accent`, `--text-primary/secondary/muted`, and the role
  pairs `--bg-danger`/`--text-danger`, `--bg-warning`/`--text-warning`,
  `--bg-success`/`--text-success`, `--bg-accent`/`--text-accent`, plus `--radius`.
- **Icons: Tabler outline only** (`<i class="ti ti-…">`). No emoji.
- **Sentence case everywhere.** Font weight 400 or 500 only (never bold headers).
- **Buttons are pre-styled** — write a bare `<button>`, no inline button colors.
- A button that hands off to Claude uses `onclick="sendPrompt('…')"` and its
  visible label ends with ` ↗`.
- Start with a screen-reader summary: `<h2 class="sr-only">…</h2>`.

### Field → card mapping

| Play field | Where it goes |
|------------|---------------|
| `variant`  | icon color + chip color: `error`→`--*-danger`, `warning`→`--*-warning`, `recommended`→`--*-success` |
| `key`      | the Tabler icon (see icon map); fall back by `variant` (`error`→`ti-alert-triangle`, `warning`→`ti-clock`, `recommended`→`ti-circle-check`) |
| `eyebrow`  | the status chip label — verbatim, already sentence case |
| `title`    | card title — `<p>` at `font-weight:500;font-size:15px` — verbatim |
| `why`      | card body — `<p style="color:var(--text-secondary);font-size:13px">` — verbatim (it cites the real numbers) |
| `button`   | the button label + ` ↗` — verbatim |
| `button` + `why` + `skill_chain` | the `sendPrompt('…')` argument: one natural first-person message that names the record and numbers and walks the chain (see below) |
| `signal` (when set) | a muted source chip under the body: source icon + `Slack · 2h ago` |

**Icon map** (by `key`): `deal_gone_quiet`→`ti-volume-off`,
`call_today_no_prep`→`ti-calendar`, `pipeline_hygiene`→`ti-list-check`,
`log_call_outcome`→`ti-phone-check`, `close_date_slipping`→`ti-clock-exclamation`,
`untouched_new_leads`→`ti-user-plus`, `renewal_horizon`→`ti-refresh`,
`forecast_gap`→`ti-target`, `team_pipeline_coverage`→`ti-users`,
`deal_needs_review`→`ti-clipboard-check`, `rep_needs_coaching`→`ti-school`,
`account_at_risk`→`ti-activity-heartbeat`. Signals:
`meeting_external`→`ti-calendar-event`, `inbound_reply_due`→`ti-mail`,
`customer_message`→`ti-brand-slack`.

**`sendPrompt` argument.** Expand `button` + `why` + `skill_chain` into one
natural, first-person message so the tap runs the mapped play. For the chain
`["deal-signals","deal-advance-gap","draft-outreach"]`: `Help me re-engage Acme
Corp: pull the deal signals on the $95,000 opportunity that closes in 4 days,
diagnose what is stalling it, and draft outreach to re-engage the buyer.` Keep
it specific; never paste the raw skill names. **Escape** any apostrophe inside
the string as `\'` (or rephrase to avoid it, e.g. "what is" not "what's") — an
unescaped `'` breaks the `onclick`.

### Canonical fragment (sample book — the Jordan Rivera Top 3)

```html
<h2 class="sr-only">Your top three next-best plays: re-engage Acme Corp, prep today's Hooli call, and fix three deals missing a next step.</h2>
<div style="display:flex;justify-content:flex-end;padding:0 0 8px;">
  <span style="font-size:12px;background:var(--bg-warning);color:var(--text-warning);padding:2px 10px;border-radius:var(--radius);">Sample data</span>
</div>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;">
  <div style="background:var(--surface-2);border:0.5px solid var(--border);border-radius:12px;padding:1rem 1.25rem;display:flex;flex-direction:column;gap:10px;">
    <div style="display:flex;align-items:center;gap:8px;"><i class="ti ti-volume-off" style="font-size:20px;color:var(--text-danger)" aria-hidden="true"></i><span style="font-size:12px;background:var(--bg-danger);color:var(--text-danger);padding:2px 8px;border-radius:var(--radius);">Re-engage</span></div>
    <p style="font-weight:500;font-size:15px;margin:0;">Acme Corp's deal has gone quiet</p>
    <p style="font-size:13px;color:var(--text-secondary);margin:0;flex:1;line-height:1.5;">Acme Corp ($95,000) closes in 4 days and has had no activity in 12 days.</p>
    <button onclick="sendPrompt('Help me re-engage Acme Corp: pull the deal signals on the $95,000 opportunity that closes in 4 days, diagnose what is stalling it, and draft outreach to re-engage the buyer.')">Help me re-engage Acme Corp ↗</button>
  </div>
  <div style="background:var(--surface-2);border:0.5px solid var(--border);border-radius:12px;padding:1rem 1.25rem;display:flex;flex-direction:column;gap:10px;">
    <div style="display:flex;align-items:center;gap:8px;"><i class="ti ti-calendar" style="font-size:20px;color:var(--text-warning)" aria-hidden="true"></i><span style="font-size:12px;background:var(--bg-warning);color:var(--text-warning);padding:2px 8px;border-radius:var(--radius);">Call prep</span></div>
    <p style="font-weight:500;font-size:15px;margin:0;">You have a call today with no prep</p>
    <p style="font-size:13px;color:var(--text-secondary);margin:0;flex:1;line-height:1.5;">Call with Hooli today at 14:00 on a $120,000 deal — no prep logged yet.</p>
    <button onclick="sendPrompt('Prep my 2:00pm call with Hooli on the $120,000 deal: assemble the account context, a call-prep brief, and the stakeholder map.')">Prep my call with Hooli ↗</button>
  </div>
  <div style="background:var(--surface-2);border:0.5px solid var(--border);border-radius:12px;padding:1rem 1.25rem;display:flex;flex-direction:column;gap:10px;">
    <div style="display:flex;align-items:center;gap:8px;"><i class="ti ti-list-check" style="font-size:20px;color:var(--text-success)" aria-hidden="true"></i><span style="font-size:12px;background:var(--bg-success);color:var(--text-success);padding:2px 8px;border-radius:var(--radius);">Quick win</span></div>
    <p style="font-weight:500;font-size:15px;margin:0;">3 deals are missing a next step</p>
    <p style="font-size:13px;color:var(--text-secondary);margin:0;flex:1;line-height:1.5;">3 open deals are missing a next step (one is already past its close date).</p>
    <button onclick="sendPrompt('Clean up my pipeline: show the 3 open deals missing a next step (including the one past its close date) and help me set the right next step on each.')">Clean up my pipeline ↗</button>
  </div>
  <div style="grid-column:1/-1;background:var(--surface-1);border:0.5px solid var(--border-accent);border-radius:12px;padding:0.875rem 1.25rem;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
    <span style="font-size:13px;color:var(--text-secondary);">These come from First Move's sample book. Your Salesforce is connected — rank your real book the same way.</span>
    <button onclick="sendPrompt('Run First Move on my live Salesforce book and show my real top 3 plays.')">Run on my live data ↗</button>
  </div>
</div>
```

### Sample vs. live

- **Status chip (top-right).** Sample book: `Sample data` on `--bg-warning`.
  Live org: `Live · <org>` on `--bg-success`.
- **Connect card (last, full width, sample only).** The `grid-column:1/-1` card
  above, inviting a live run. On a **live** render, **drop that card entirely**.
- **Reply text (outside the widget).** Say it plainly in your message next to the
  widget, e.g. sample: *"Here are your top three plays from First Move's sample
  book (Jordan Rivera) — your live Salesforce is connected, so I can rank your
  real book instead."*; live: *"Here are your top three plays from your live
  Salesforce book as of <date>."*

### Signals in the render

The engine already folds cross-connector signals into the JSON, so most of this
is automatic:

- **Enriched Salesforce play** (`signal` set, `origin:"salesforce"`): the `why`
  already has the signal note appended by the engine — render it verbatim. Add a
  muted source chip under the body: `<span style="font-size:12px;color:var(--text-muted);display:inline-flex;align-items:center;gap:4px;"><i class="ti ti-brand-slack" aria-hidden="true"></i>Slack · 2h ago</span>`.
- **Workspace play** (`origin:"workspace"`): renders as an ordinary card. Its
  `eyebrow` (`Meeting` / `Reply due` / `Slack`) already signals provenance; use
  the signal icon map for the card icon and add the same source chip.

---

## Alternate renderer — Salesforce Mosaic `display_widget`

On a Salesforce-native MCP-Apps surface, render the same plays as Mosaic tiles
with the Salesforce connector's `display_widget`:

- Call with `resourceType: "dynamic"` and `widgetDefinition` as a **native JSON
  object** — never a stringified JSON string.
- When `display_widget` succeeds, **that tool call is the final output** — do not
  append a prose summary underneath.
- Every button must be one `action/sendMessage` (a natural first-person message,
  same expansion as Path 1) or one `action/openLink`. No other action types. No
  charts.
- Mosaic eyebrows are conventionally uppercase: render the eyebrow as
  `PLAY {n} · {EYEBROW} · {EFFORT} EFFORT` (upper-case the sentence-case
  `eyebrow` from the data).

Root is `renderer.componentOverrides.$`, a `tile/mosaic` whose `children` are a
header row (`tile/text` `variant:"h1"` + `tile/badge`), a caption, a
section-title, one `tile/callout` per play (each holding one `tile/button`), then
a footer connect callout (sample only). Known-good envelope:

```json
{
  "renderer": {
    "componentOverrides": {
      "$": {
        "type": "mosaic",
        "definition": "tile/mosaic",
        "children": [
          {
            "definition": "tile/row",
            "attributes": { "gap": "sm", "align": "center", "justify": "between", "isWrapped": true },
            "children": [
              { "definition": "tile/text",  "attributes": { "text": "First Move", "variant": "h1" } },
              { "definition": "tile/badge", "attributes": { "label": "SAMPLE DATA", "variant": "warning" } }
            ]
          },
          { "definition": "tile/text", "attributes": { "text": "Your top 3 next-best plays for today, ranked from your book — Jordan Rivera · Account Executive", "variant": "caption", "color": "muted" } },
          { "definition": "tile/text", "attributes": { "text": "Top 3 Plays", "variant": "section-title" } },

          {
            "definition": "tile/callout",
            "attributes": {
              "variant": "error",
              "eyebrow": "PLAY 1 · RE-ENGAGE · MEDIUM EFFORT",
              "title": "Acme Corp's deal has gone quiet",
              "description": "Acme Corp ($95,000) closes in 4 days and has had no activity in 12 days."
            },
            "children": [
              {
                "definition": "tile/button",
                "attributes": {
                  "label": "Help me re-engage Acme Corp",
                  "variant": "primary",
                  "actions": { "click": [ { "definition": "action/sendMessage", "attributes": { "content": "Help me re-engage Acme Corp: pull the deal signals on the $95,000 opportunity that closes in 4 days, diagnose what is stalling it, and draft outreach to re-engage the buyer." } } ] }
                }
              }
            ]
          },

          {
            "definition": "tile/callout",
            "attributes": {
              "variant": "warning",
              "eyebrow": "PLAY 2 · CALL PREP · LOW EFFORT",
              "title": "You have a call today with no prep",
              "description": "Call with Hooli today at 14:00 on a $120,000 deal — no prep logged yet."
            },
            "children": [
              {
                "definition": "tile/button",
                "attributes": {
                  "label": "Prep my call with Hooli",
                  "variant": "primary",
                  "actions": { "click": [ { "definition": "action/sendMessage", "attributes": { "content": "Prep my 2:00pm call with Hooli on the $120,000 deal: assemble the account context, a call-prep brief, and the stakeholder map." } } ] }
                }
              }
            ]
          },

          {
            "definition": "tile/callout",
            "attributes": {
              "variant": "recommended",
              "eyebrow": "PLAY 3 · QUICK WIN · LOW EFFORT",
              "title": "3 deals are missing a next step",
              "description": "3 open deals are missing a next step (one is already past its close date)."
            },
            "children": [
              {
                "definition": "tile/button",
                "attributes": {
                  "label": "Clean up my pipeline",
                  "variant": "primary",
                  "actions": { "click": [ { "definition": "action/sendMessage", "attributes": { "content": "Clean up my pipeline: show the 3 open deals missing a next step (including the one past its close date) and help me set the right next step on each." } } ] }
                }
              }
            ]
          },

          {
            "definition": "tile/callout",
            "attributes": {
              "variant": "recommended",
              "eyebrow": "CONNECTED",
              "title": "Want these from your real book?",
              "description": "These three come from First Move's bundled sample data. Your Salesforce is connected — First Move can rank your live opportunities, calls, and leads the same way."
            },
            "children": [
              {
                "definition": "tile/button",
                "attributes": {
                  "label": "Run First Move on my live data",
                  "variant": "secondary",
                  "actions": { "click": [ { "definition": "action/sendMessage", "attributes": { "content": "Run First Move on my live Salesforce book and show my real top 3 plays." } } ] }
                }
              }
            ]
          }
        ]
      }
    }
  }
}
```

**Tile vocabulary:** `tile/mosaic` (root, `children`); `tile/row` (`gap`,
`align`, `justify`, `isWrapped`); `tile/text` (`text` + `variant`
`h1`/`section-title`/`caption`/`body` + optional `color:"muted"`); `tile/badge`
(`label` + `variant` `success`/`warning`/`error`/`secondary`/`outline`);
`tile/callout` (`variant` `error`/`warning`/`recommended`, `eyebrow`, `title`,
`description`; `children` = button(s)); `tile/button` (`label`, `variant`
`primary`/`secondary`, optional `iconName`, `actions.click` = one
`action/sendMessage` `content` or `action/openLink` `url`).

---

## Fallback — no widget renderer

If neither renderer is available (e.g. a plain terminal), present a **tight
numbered list**: for each play, its `title`, the one-line `why` verbatim, and the
`button` label as `[ … ]`. Three items, then let the seller pick one. State the
sample-vs-live line and the live-run offer in the same message.

# OTA-621 — Structured markdown export from trade and position cards for claude.ai QA handoff

## Deployment context
- Deployment: **D3**
- This terminal: **T3**
- Concurrent terminals: T1 (`OTA-624` persist trade candidates — disjoint files), T2 (`OTA-629` per-watchlist scan cache — disjoint files)
- Cross-terminal dependencies: **none** — T3 adds a new export route and Export-MD buttons; T1 and T2 do not touch these files

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/UI-GUIDANCE.md
cat claude_context/auth-process.md
```

Plus:

```
cat /mnt/skills/user/options-analyzer-qa/SKILL.md    # Step 0 parse fields are the alignment target
cat web/src/pages/TradesPage.jsx                     # Follow / Take Position buttons — siblings for Export MD
cat web/src/pages/PositionsPage.jsx                  # parallel surface
grep -rn "Content-Disposition" app/                  # any existing download pattern
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: options-analyzer-qa SKILL.md § Step 0**
The QA skill's Step 0 parse looks for these fields. **Field labels in the exported markdown must match what the skill keys off:**
- Ticker, spread type, strikes, expiration
- Entry price (debit cost or credit received)
- App verdict: EXECUTE / WAIT / PASS
- App score (0–100)
- App score breakdown (if present)
- App narrative ("Claude's Read")
- App invalidation conditions ("This Trade Is Wrong If")

If the labels in the export drift from what the skill parses, the QA handoff fails silently. Pin the labels.

**Source: architecture-plan.md § Data Isolation Invariant**
Every CRUD endpoint that takes a resource ID filters by `user_id`. Both new endpoints in this Story are subject. Cross-user attempts return 404 (not 403).

**Source: architecture-plan.md § Pattern 2 (Skill-Driven Prompts)**
Skill files are the sole source of prompt content; no hardcoded prompts in Python or React. This Story does not create or modify a prompt; it produces structured markdown for handoff to a claude.ai skill. The export format is data-only — no instructions embedded.

**Source: CLAUDE.md § House style**
- Buttons sized to content, never full-width; visible border or background in default state
- No `$` prefix on monetary values
- Scores formatted `##.00`
- Dates `mm-dd-yyyy`
- `var(--bg2)` restricted to filter bars, QuoteBar, and pill badge backgrounds — not used for the Export MD button

**Source: CLAUDE.md § Trade type badges**
Bull trades green, bear red; title-case display names, no underscores. The export markdown should use the same display names (e.g., "Bull Put Credit", not `bull_put_credit`) where the QA skill expects human-readable labels — but check Step 0 to see if the skill parses the raw identifier or the display label.

---

## Scope

### 1. Backend — new export endpoints

In `app/api/export_routes.py` (NEW):

**`GET /api/v1/export/trade/{trade_key}.md`**

- Filters by `(trade_key, user_id)`; returns 404 if not found.
- Reads from `trade_candidates` if available (post-OTA-624). If OTA-624 hasn't shipped on this deploy, falls back to reading the trade from the latest scan results in session storage — **escalate to Don** if the data source is unclear; do not invent a fallback path.
- Returns `text/markdown` with `Content-Disposition: attachment; filename="{symbol}_{strikes}_{spread_type}.md"`.
- Body is the structured markdown described in section 3.

**`GET /api/v1/export/position/{position_id}.md`**

- Filters by `(position_id, user_id)`; returns 404 if not found.
- Reads from the `positions` table and joins the latest `position_assessments` row.
- Returns `text/markdown` with `Content-Disposition: attachment; filename="{symbol}_position_{position_id}.md"`.

### 2. Filename pattern

`{symbol}_{strikes}_{spread_type_label}.md` for trade exports — e.g., `AAPL_180-185_bull_put_credit.md`.

`{symbol}_position_{position_id}.md` for position exports — e.g., `AAPL_position_42.md`.

Sanitize symbol and labels for filesystem safety (no slashes, spaces → underscores).

### 3. Markdown body — structured contract

Trade export body (pin these labels to match options-analyzer-qa Step 0):

```markdown
# Trade Candidate — {SYMBOL}

**Exported:** {ISO 8601 timestamp UTC}
**Trade key:** {trade_key}

## Trade structure

- **Ticker:** {SYMBOL}
- **Spread type:** {Bull Put Credit | Bear Call Credit | Long Call | etc. — display label}
- **Strikes:** {short_strike}/{long_strike} (or single strike)
- **Expiration:** {mm-dd-yyyy}
- **DTE:** {n}
- **Quantity:** {n} contracts

### Legs

| Side | Type | Strike | Expiration | Qty | Bid | Ask | Delta | IV |
|---|---|---|---|---|---|---|---|---|
| {long/short} | {call/put} | {strike} | {mm-dd-yyyy} | {qty} | {bid} | {ask} | {delta} | {iv} |

## Net metrics

- **Entry price:** {debit cost or credit received, formatted ##.00, NO $ prefix}
- **Max profit:** {##.00}
- **Max loss:** {##.00}
- **Breakeven:** {price or [lower, upper]}
- **Net bid-ask:** {##.00}
- **Underlying spot:** {##.00}
- **IV Rank:** {##.00%}
- **Scenario-weighted EV:** {##.00}
- **Probability of profit:** {##.00%}

## App verdict: {EXECUTE | WAIT | PASS}

**App score:** {##.00}

### App score breakdown

(only if `pipeline_components` is present)

- {component_name}: {value}
- ...

### App narrative ("Claude's Read")

{claude_read text — full, not truncated}

### This Trade Is Wrong If

(only if `thesis_invalidators` is non-empty)

- {invalidator 1}
- {invalidator 2}
- ...

### Key risks

(only if `key_risks` is non-empty)

- {risk 1}
- ...

## Probability matrix

(only if `probability_matrix` is present)

| Scenario | Probability | P&L |
|---|---|---|
| {name} | {##.00%} | {##.00} |
| ...

---

*Generated by Options Analyzer for QA handoff via the `options-analyzer-qa` skill on claude.ai. Field labels are pinned to that skill's Step 0 parse contract.*
```

Position export body — adds these sections at the top instead of "Trade Candidate":

```markdown
# Position — {SYMBOL} (id {position_id})

**Status:** {FOLLOWING | TAKEN | CLOSED}
**Followed at:** {mm-dd-yyyy}
**Last monitored:** {mm-dd-yyyy hh:mm UTC}
**Current price:** {##.00}
**Current P&L:** {±##.00}
```

Followed by the same trade structure / verdict / narrative sections, but using the latest assessment values (post-OTA-630, refresh-mirrored on `positions`).

### 4. Frontend — Export MD buttons

**Trades page (`web/src/pages/TradesPage.jsx`)**

- Add "Export MD" button to every trade card, sibling to Follow / Take Position.
- Sized to content; visible border in default state.
- onClick: `window.location.href = '/api/v1/export/trade/' + trade_key + '.md'` — relies on `Content-Disposition: attachment` to trigger browser download.

**Positions page (`web/src/pages/PositionsPage.jsx`)**

- Add "Export MD" button to every position card.
- onClick: `window.location.href = '/api/v1/export/position/' + position_id + '.md'`.

If the same button component is duplicated, extract a `<ExportMdButton>` shared component. Optional — implementer's call.

### 5. Auth

Endpoints are session-authenticated like all other `/api/v1/*` routes — BFF session cookie, CSRF token if the route is non-GET. These are GETs, so CSRF is not required. Verify the BFF middleware applies.

---

## Acceptance criteria

1. `GET /api/v1/export/trade/{trade_key}.md` returns a `text/markdown` body matching the contract above; `Content-Disposition: attachment` triggers download.
2. `GET /api/v1/export/position/{position_id}.md` returns a `text/markdown` body for the position; latest assessment values used.
3. Both endpoints return 404 for cross-user IDs (Data Isolation Invariant).
4. Both endpoints return 404 for non-existent IDs.
5. Field labels in the markdown match `options-analyzer-qa` SKILL.md Step 0 parse exactly. Manual verification: feed an exported file to the QA skill in a claude.ai session and confirm Step 0 succeeds.
6. Filename pattern is correct and filesystem-safe.
7. Trades page Export MD button appears on every card, sibling to Follow / Take Position.
8. Positions page Export MD button appears on every position card.
9. Button styling matches CLAUDE.md house style — sized to content, visible border, no `$` prefix anywhere in the export body, scores `##.00`, dates `mm-dd-yyyy`.
10. No `var(--bg2)` on the new buttons.
11. Exporting a card whose `key_risks` is empty omits the Key risks section (no empty "Key risks" header).
12. Exporting a card with no `pipeline_components` omits the score breakdown section.

---

## Out of scope

- JSON export (markdown only for v1).
- "Export all" or bulk export action.
- Server-side persistence of exports.
- A claude.ai connector / web fetcher to pull exports automatically (the user copies/uploads the file manually).
- Localization of date format (UTC ISO + mm-dd-yyyy throughout; per CLAUDE.md house style).

---

## Verification steps (run before commit)

1. **Manual smoke (dev frontend):**
   - Trades page → click Export MD on a card → file downloads → open in editor → contents match contract.
   - Positions page → click Export MD on a position → file downloads → contents match contract.
   - Feed the downloaded trade file to the `options-analyzer-qa` skill on claude.ai (separate session) → Step 0 parse succeeds and identifies all fields.
2. **Async pytest:**
   - `GET /api/v1/export/trade/{trade_key}.md` with a valid trade → 200, body contains `# Trade Candidate`, `**Spread type:**`, `**App verdict:**`, etc.
   - Same endpoint with cross-user trade → 404.
   - Same endpoint with non-existent trade → 404.
   - Same for the position endpoint.
3. **Format compliance** — body has no `$` prefix on monetary values; scores formatted `##.00`; dates `mm-dd-yyyy`.
4. **Defensive against missing fields** — export a trade with `key_risks=[]` → markdown omits the section.
5. **No regression** in existing routes or pages. Existing tests pass.
6. **Auth check** — unauthenticated request to either endpoint → 401 from BFF middleware. (Verify by clearing session cookie and curling.)

If any verification fails, stop and report.

---

## Commit instruction

**I have been instructed to commit. Do you approve? (yes / no)**

One commit covers OTA-621.

## Push instruction

**DO NOT push. Single push for Deployment 3 will be coordinated by Don after all D3 terminals (T1, T2, T3) report commit.**

## Coordination footer

**Independent — no downstream dependency.** This terminal closes after committing.

## Commit message template

```
OTA-621 feat: structured markdown export from trade and position cards for options-analyzer-qa handoff
```

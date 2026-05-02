---
allowedTools: [Bash, Read, Write, Edit]
---

# OTA-264 + OTA-266 — Position Refresh Endpoint + Synopsis Generation

**Jira:** OTA-264, OTA-266 | Parent: OTA-262 (Position Assessment Versioning)
**Priority:** Medium
**Run in parallel with OTA-296. Independent of OTA-325/326.**

---

## Before You Start

```bash
cat app/api/evaluation_routes.py
cat app/models/schemas.py
cat app/skills/claude-trade-agent/SKILL.md
grep -n "position_assessments\|positions\|assessment_type" app/models/database.py
grep -n "TradeVerdict\|structured\|verdict" app/models/schemas.py
grep -rn "agent_run_log" app/api/
```

Read all output completely before making any changes.

---

## Context

Two related tickets are batched here:

- **OTA-264:** Build `POST /api/v1/positions/{id}/refresh` — re-run Claude analysis with
  current market data, write a new `position_assessments` row
- **OTA-266:** Add `synopsis` field to the evaluation SKILL.md — 5–7 word summary of
  whether original thesis holds or what changed

---

## OTA-266 — Add Synopsis to SKILL.md (Do This First)

Before building the endpoint, add the `synopsis` output field to
`app/skills/claude-trade-agent/SKILL.md`.

### Synopsis Field Spec

Add `synopsis` as a sixth field in the structured JSON output:

```json
{
  "ev_commentary": "...",
  "key_level": { "price": 0.00, "description": "..." },
  "iv_context": "...",
  "verdict": "EXECUTE | WATCH | PASS",
  "verdict_rationale": "...",
  "synopsis": "5–7 word summary of thesis status"
}
```

**Synopsis rules (add to static section of SKILL.md):**
- Exactly 5–7 words
- Written in present tense
- Describes whether the original thesis holds, is strengthening, weakening, or broken
- Examples:
  - `"IV expanding, thesis strengthening slightly"`
  - `"Bullish rally pressuring thesis, hold for now"`
  - `"Thesis intact, price holding above short strike"`
  - `"Time decay accelerating, original thesis eroding"`
- Do NOT include numbers or prices in synopsis (those are in other fields)
- Used as the collapsed-view header on the Positions page

**Also add to the dynamic user message section:**
When this is an UPDATE assessment (not initial), inject all prior assessments so Claude can
reference its own analysis evolution. Format:

```
Prior assessments (oldest first):
[assessment_date]: verdict=[VERDICT] synopsis=[SYNOPSIS] key_level=[PRICE]
```

---

## OTA-264 — Position Refresh Endpoint

### Route

`POST /api/v1/positions/{id}/refresh`

File: `app/api/evaluation_routes.py` (or create `position_routes.py` if this route
logically belongs there — check what exists)

### Logic Flow

1. **Read position from DB** — fetch the position row by `id`. If not found, raise 404.
   Capture: `symbol`, `strategy`, `spread_type`, `strikes`, `expiry`, `entry_price`,
   `max_profit`, `max_loss`, all entry-time values.

2. **Fetch current market data** — call `_get_provider()` for:
   - Current quote: `provider.get_quote(symbol)` → `current_price`, `iv`
   - Options chain: `provider.get_chain(symbol)` — extract current prices at the
     position's strikes

3. **Fetch prior assessments** — query `position_assessments` table for all rows where
   `position_id = id`, ordered by `created_at` ASC. Pass to Claude as history context.

4. **Call Claude via existing pattern** — load the SKILL.md prompt via `skill_loader.py`,
   inject original entry context + current data + prior assessment history.
   Use the existing `TradeVerdict` Pydantic model for the response.

5. **Write new assessment row** — insert into `position_assessments`:
   - `position_id` = id
   - `assessment_type` = `"UPDATE"`
   - `verdict`, `score`, `synopsis`, `claude_read`, `exit_levels` from Claude response
   - `created_at` = now UTC

6. **Write agent_run_log row** — follow existing pattern in `evaluation_routes.py`.

7. **Return** the new assessment as structured JSON response.

### Response Schema

Add to `app/models/schemas.py` if not already present:

```python
class PositionAssessmentResponse(BaseModel):
    assessment_id: str
    position_id: str
    assessment_type: str  # "INITIAL" | "UPDATE"
    verdict: str          # "EXECUTE" | "WATCH" | "PASS"
    score: float          # 0–100
    synopsis: str         # 5–7 words
    claude_read: str      # full narrative
    exit_levels: dict
    created_at: str       # mm-dd-yyyy hh:mm
```

### Error Handling

- 404 if position not found
- 503 if Schwab provider unavailable
- 500 with descriptive message if Claude call fails — do NOT write partial DB row on failure

---

## Acceptance Criteria

- [ ] `synopsis` field added to SKILL.md structured output spec
- [ ] Prior assessment history injected in UPDATE calls (dynamic section)
- [ ] `POST /api/v1/positions/{id}/refresh` route exists and responds
- [ ] New `position_assessments` row written with `assessment_type=UPDATE`
- [ ] `agent_run_log` row written on every invocation
- [ ] Response includes all six structured fields including `synopsis`
- [ ] 404 returned for unknown position ID
- [ ] No hardcoded prompts in Python — SKILL.md is the sole prompt source
- [ ] `_get_provider()` used — never hardcoded `"schwab"` or `"tradier"`

---

## House Style Rules

- Date format `mm-dd-yyyy` via `formatDate()` on frontend; ISO UTC in DB
- Position source labels: "Paper" / "Live" (not "PAPER"/"LIVE")
- Health grades: A/B/C/D/F with color — not numeric

---

## Commit Message

```
OTA-264 OTA-266 Add synopsis to SKILL.md, build position refresh endpoint with assessment versioning
```

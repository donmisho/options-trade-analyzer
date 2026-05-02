---
allowedTools: [Bash, Read, Write, Edit]
---

# OTA-296 — Update claude-trade-agent SKILL.md with Structured Evaluation Prompt

**Jira:** OTA-296 | Parent: OTA-289 (Section E — Structured Claude's Read)
**Priority:** Medium | **Labels:** framework-portable, options-domain, requirement

---

## Before You Start

```bash
cat app/skills/claude-trade-agent/SKILL.md
cat app/providers/ai/base.py
cat app/providers/ai/prompts.py
grep -n "TradeVerdict\|TradeContext\|verdict\|structured" app/models/schemas.py
```

Read all files completely before making any changes.

---

## Goal

Replace or update the system prompt in `app/skills/claude-trade-agent/SKILL.md` with the
structured evaluation prompt spec below. This SKILL.md is the **sole** source of truth for
the Claude trade evaluation prompt — it must never be hardcoded in Python or React.

---

## Structured Evaluation Prompt Specification

### Inputs Claude Receives (pre-computed — Claude does NOT recalculate any of these)

| Field | Type | Description |
|-------|------|-------------|
| `spread_type` | string | e.g. "bull_put_spread", "bear_call_spread" |
| `strikes` | object | `{ short: float, long: float }` |
| `expiry` | string | `mm-dd-yyyy` format |
| `entry_price` | float | Net credit received (positive = credit) |
| `max_profit` | float | Dollar max profit |
| `max_loss` | float | Dollar max loss |
| `breakeven` | float | Breakeven price level |
| `dte` | int | Days to expiration |
| `ev` | float | Expected value in dollars |
| `ev_pct_of_risk` | float | EV as % of max risk |
| `p_max_profit` | float | Probability of max profit (0–1) |
| `p_breakeven_or_better` | float | Probability at or above breakeven (0–1) |
| `p_max_loss` | float | Probability of max loss (0–1) |
| `iv` | float | Implied volatility (stored as decimal, e.g. 0.35 = 35%) |

### Required Output — JSON object with exactly these five fields

```json
{
  "ev_commentary": "string — plain language interpretation of EV sign and magnitude",
  "key_level": {
    "price": "float — the single most important price to watch",
    "description": "string — brief explanation of why this level matters"
  },
  "iv_context": "string — whether IV at this level favours this trade direction",
  "verdict": "EXECUTE | WATCH | PASS",
  "verdict_rationale": "string — one to two sentences justifying the verdict"
}
```

### Prompt Caching Requirements

The SKILL.md must clearly delimit:
- **Static system prompt section** — defines Claude's role, output format, JSON schema,
  and rules. This section is cacheable (never changes per call).
- **Dynamic user message section** — the trade data injected per evaluation call. This
  section is not cached.

Label them explicitly with comments or section headers within the SKILL.md so the
Python adapter can apply `cache_control: {"type": "ephemeral"}` to the static block.

### Behavioral Rules in the Prompt

Include these rules explicitly in the static section:

1. **Never recalculate probabilities.** All math arrives pre-computed. Use the provided
   values only.
2. **Output only valid JSON.** No markdown fences, no preamble, no explanation outside
   the JSON object.
3. **Verdict logic guidance:**
   - EXECUTE: EV positive, PoP ≥ 65%, IV context favorable
   - WATCH: EV positive but marginal, or one factor borderline
   - PASS: EV negative, PoP < 55%, or IV strongly unfavorable
4. **Key level selection:** Choose the single price level most relevant to the trade's
   success or failure (e.g. short strike for credit spreads, breakeven for debit spreads).
5. **Probabilities display as percentages in rationale** (e.g. "68% chance of profit")
   even though they arrive as decimals.

---

## What NOT to Change

- Do not modify the folder structure under `app/skills/`
- Do not add any prompt content to `prompts.py`, `anthropic_adapter.py`, or any `.py` file
- Do not change the `skill_loader.py` loading convention

---

## Acceptance Criteria

- [ ] `app/skills/claude-trade-agent/SKILL.md` exists and contains the full structured prompt
- [ ] Static and dynamic sections are clearly delimited with comments
- [ ] All five required output fields are defined in the SKILL.md
- [ ] Behavioral rules (no recalculation, JSON-only output, verdict logic) are present
- [ ] File contains no hardcoded Python, no import statements, no code blocks
- [ ] Existing SKILL.md content that is still valid is preserved or superseded cleanly

---

## Commit Message

```
OTA-296 Update claude-trade-agent SKILL.md with structured evaluation prompt and caching delimiters
```

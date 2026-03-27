# Claude Code Prompt — OTA-296
## Update claude-trade-agent SKILL.md with Structured Evaluation Prompt

### Ticket
- OTA-296: Update `app/skills/claude-trade-agent/SKILL.md` with the structured evaluation prompt

---

### Before You Start

```bash
cat app/skills/claude-trade-agent/SKILL.md
cat app/skill_loader.py
```

Read both. You are editing the existing SKILL.md — do not recreate it from scratch. Append the new structured evaluation section while preserving everything already there.

---

### What to Add

Add a new section to `app/skills/claude-trade-agent/SKILL.md` titled **"Structured Trade Evaluation"**.

This section contains the prompt for the `/evaluate/structured` endpoint. It must have two clearly delimited parts so prompt caching can be applied to the static system prompt portion:

---

#### Section structure to add:

```markdown
## Structured Trade Evaluation

### System Prompt (static — cache this section)

You are a professional options trade analyst. You receive pre-computed spread economics and probability data. Your job is to provide a structured trade evaluation. You do not recalculate any probabilities or math — all numbers are provided to you.

Rules:
- Return ONLY a valid JSON object. No preamble, no markdown fences, no explanation outside the JSON.
- All five fields are required. Never omit a field.
- ev_commentary: 1–2 sentences interpreting the sign and magnitude of the expected value in plain English. Do not restate the number — explain what it means for this trade.
- key_level: The single most important price level to watch (not the breakeven — pick the level that would change your conviction). price must be a float. description must be a short phrase.
- iv_context: 1 sentence on whether current IV favors or works against this trade direction.
- verdict: One of exactly: EXECUTE, WATCH, or PASS. No other values.
- verdict_rationale: 1–2 sentences justifying the verdict. Reference at least one specific number from the input.

### User Prompt Template (dynamic — do not cache)

Evaluate this vertical spread:

Spread: {spread_type}
Strikes: {long_strike} / {short_strike}
Expiry: {expiry} ({dte} DTE)
Entry: {entry_price} per share
Max Profit: {max_profit} | Max Loss: {max_loss}
Breakeven: {breakeven}
R:R: {reward_risk}

Probability Analysis:
- P(Max Profit): {p_max_profit}%
- P(Breakeven or Better): {p_breakeven_or_better}%
- P(Max Loss): {p_max_loss}%
- Expected Value: {total_ev} ({ev_pct_of_risk}% of risk)

IV: {iv}

Return this exact JSON structure:
{
  "ev_commentary": "string",
  "key_level": { "price": float, "description": "string" },
  "iv_context": "string",
  "verdict": "EXECUTE" | "WATCH" | "PASS",
  "verdict_rationale": "string"
}
```

---

### Rules for This Edit

- Do not modify any other section of SKILL.md
- The section delimiter comment `### System Prompt (static — cache this section)` must remain exactly as written — the backend uses it for prompt caching boundary detection
- The template placeholders use `{field_name}` format — do not change them
- No dollar signs anywhere in the prompt text

---

### Verify

After editing, confirm:
```bash
grep -n "Structured Trade Evaluation" app/skills/claude-trade-agent/SKILL.md
grep -n "static — cache this section" app/skills/claude-trade-agent/SKILL.md
grep -n "EXECUTE\|WATCH\|PASS" app/skills/claude-trade-agent/SKILL.md
```

All three must return results. If any grep returns nothing, the edit is incomplete.

---

### Commit Message
```
OTA-296 docs: structured evaluation prompt in claude-trade-agent SKILL.md
```

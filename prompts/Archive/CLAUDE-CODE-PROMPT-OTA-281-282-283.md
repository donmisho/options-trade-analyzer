# Claude Code Prompt — OTA-281 OTA-282 OTA-283
## Vertical Engine Greek Filter & P&L Formula Fixes

### Tickets
- OTA-281: Max Net Theta = 0 should disable the filter (sentinel fix)
- OTA-282: Delta filters must use abs() for put legs and net delta
- OTA-283: Debit and Credit max profit / max loss formulas are wrong

---

### Before You Start

```bash
cat app/engines/vertical_engine.py
```

Read the entire file before making any changes. Do not rely on assumptions about what's there.

---

### Fix 1 — OTA-281: Max Net Theta Sentinel (vertical_engine.py)

**Problem:** When `max_net_theta = 0`, the filter currently blocks all spreads because it compares `abs(net_theta) <= 0`, which is almost never true. A value of 0 should mean "disabled — let everything through."

**Change:** In the theta gate logic, treat 0 as disabled:

```python
# BEFORE (approximate — match actual code pattern):
if max_net_theta and abs(net_theta) > max_net_theta:
    continue

# AFTER:
if max_net_theta != 0 and abs(net_theta) > max_net_theta:
    continue
```

**Acceptance criteria:**
- `max_net_theta = 0` allows all spreads through regardless of theta sign or magnitude
- `BEAR_PUT_DEBIT` spreads with `net_theta = -0.08` pass when `max_net_theta = 0`
- `max_net_theta = 0.10` filters out spreads where `abs(net_theta) > 0.10`
- Credit spreads (positive theta) and debit spreads (negative theta) are treated symmetrically by the non-zero filter

---

### Fix 2 — OTA-282: Delta Filters Must Use abs() (vertical_engine.py)

**Problem:** Put legs have negative raw deltas (e.g. -0.52). Comparing raw delta against `min_delta = 0.40` fails because `-0.52 < 0.40`. All filters must use `abs()`.

**Rules:**
- `min_delta` and `max_delta` apply to the **long leg only**, using `abs(long_leg_delta)`
- Net delta = `abs(long_leg_delta) - abs(short_leg_delta)`
- `min_net_delta` filter uses `abs(net_delta) >= min_net_delta`

**Change:** Wrap all individual leg delta comparisons and net delta comparisons with `abs()`.

**Acceptance criteria:**
- Put with raw delta `-0.52` passes `min_delta = 0.40`, `max_delta = 0.60`
- `BEAR_PUT_DEBIT` 370/345 with long leg delta `~-0.52` and short leg `~-0.27` passes `min_net_delta = 0.20` (abs net = 0.25)
- No regression on `BULL_CALL_DEBIT` deltas (already positive, `abs()` is a no-op there)
- Verify `max_delta` slider in UI supports values up to 0.60 — check `web/src/` for slider config and adjust max if needed

---

### Fix 3 — OTA-283: P&L Formula Correctness (vertical_engine.py)

**Problem:** Debit and credit spread max profit / max loss / breakeven formulas are incorrect.

**Correct formulas:**

#### Debit spreads (BEAR_PUT_DEBIT, BULL_CALL_DEBIT):
```
max_profit = (spread_width - debit_paid) * 100
max_loss = debit_paid * 100
breakeven (puts) = long_strike - debit_paid
breakeven (calls) = long_strike + debit_paid
reward_risk = max_profit / max_loss  (rounded to 2 decimal places)
```

#### Credit spreads (BULL_PUT_CREDIT, BEAR_CALL_CREDIT):
```
max_profit = credit_received * 100
max_loss = (spread_width - credit_received) * 100
breakeven (puts) = short_strike - credit_received
breakeven (calls) = short_strike + credit_received
reward_risk = max_profit / max_loss  (rounded to 2 decimal places)
```

**Acceptance criteria — verify all three:**

| Spread | Entry | max_profit | max_loss | breakeven | R:R |
|--------|-------|-----------|----------|-----------|-----|
| BEAR_PUT_DEBIT 370/345 | 8.80 | 1620 | 880 | 361.20 | 1.84 |
| BEAR_CALL_CREDIT 395/420 | 5.40 | 540 | 1960 | 400.40 | 0.28 |
| BEAR_PUT_DEBIT 350/325 | 5.35 | 1965 | 535 | 344.65 | 3.67 |

---

### House Style Reminders
- No `$` prefix on any displayed value
- All numeric values formatted to `##.00`
- Do not change any unrelated logic in `vertical_engine.py`

---

### After All Three Fixes

Run the existing test suite:
```bash
cd C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer
venv\Scripts\activate
pytest tests/ -v
```

Report all failures together before fixing anything. Do not fix one at a time.

---

### Commit Message
```
OTA-281 OTA-282 OTA-283 fix: vertical engine theta sentinel, delta abs(), P&L formulas
```

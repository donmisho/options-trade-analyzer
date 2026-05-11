# OTA-629 — Per-watchlist scan cache + last-scanned indicator on cards

## Deployment context
- Deployment: **D3**
- This terminal: **T2**
- Concurrent terminals: T1 (`OTA-624` persist trade candidates — disjoint files), T3 (`OTA-621` export MD — disjoint files)
- Cross-terminal dependencies: **none** — T2 owns `web/src/pages/SecurityStrategiesPage.jsx` and an optional new helper module; T1 and T3 do not touch these

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/UI-GUIDANCE.md
cat claude_context/business-rules.md
```

Plus:

```
cat web/src/pages/SecurityStrategiesPage.jsx         # primary surface
grep -rn "ota_scan_results" web/src/                 # find current localStorage usage
grep -rn "OTA-512\\|OTA-534" web/src/                # context on prior cache work
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: business-rules.md § Cost guardrail**
Any refresh that triggers more than one Claude API call must show a confirmation dialog before firing. **This Story specifically exists to avoid re-paying for Sonnet calls** when the user navigates between watchlists. Honor that intent — never silently re-scan on watchlist switch.

**Source: UI-GUIDANCE.md § Cached state indicators**
Cards show a "Last scanned X ago" indicator beneath the symbol/price header so the user can decide whether to rescan. Relative-time format follows the SharePoint convention (see below).

**Source: UI-GUIDANCE.md § Date formatting**
Locale-aware date formatting. No year shown when the date falls in the current year. Use `Intl.DateTimeFormat` or equivalent — no `dayjs` / `luxon` / `moment` dependency added.

**Source: CLAUDE.md § OTA-512 + OTA-534 pattern**
The cache lives in `localStorage` under the key `ota_scan_results`. OTA-534 prevented the cache wipe on initial source auto-select. This Story extends the cache from single-slot to a per-watchlist map. Do not regress OTA-534's fix — initial auto-select must still not wipe.

**Source: CLAUDE.md § House style**
- No `$` prefix on monetary values
- Scores formatted `##.00`
- Dates `mm-dd-yyyy` (where absolute dates are shown)
- `var(--bg2)` restricted to filter bars, QuoteBar, pill badge backgrounds — not used for "Last scanned" text
- Dark theme CSS variables only

---

## Scope

### 1. localStorage cache shape change

From single object:

```javascript
// OLD
localStorage['ota_scan_results'] = { results, sourceId, timestamp };
```

To per-watchlist map:

```javascript
// NEW
localStorage['ota_scan_results'] = {
  <sourceId>: { results, scanned_at, version },
  <sourceId>: { results, scanned_at, version },
  ...
};
```

- `version` is a short integer; bump on any cache-shape change so legacy entries are treated as misses.
- `scanned_at` is a UTC ISO 8601 string.
- `results` shape is unchanged from current.

### 2. Legacy cache migration on load

On `SecurityStrategiesPage.jsx` initial mount:

- Read `ota_scan_results`.
- If the value shape is the OLD single-object form (has top-level `sourceId`, `results`, `timestamp`), discard it (do not attempt to migrate — discard is safer than a partial migration). Replace with `{}` (empty map).
- If the value shape is the NEW map form but any entry's `version` differs from current, treat that entry as a cache miss.

### 3. `handleSourceChange` reads from per-watchlist cache

When the user switches watchlists, `handleSourceChange` in `SecurityStrategiesPage.jsx`:

- Reads `cache[source.id]`.
- **If present** — hydrate results from the cached entry. **Do NOT wipe.** Do not auto-scan.
- **If absent** — show empty state. **Do NOT auto-scan.**

User must click Scan to populate. This matches the current OTA-534 behavior for auto-select; this Story extends it to manual switches.

### 4. `handleScan` writes only the active watchlist's entry

When the user scans:

- Update `cache[selectedSource.id] = { results, scanned_at: <now>, version: <current> }`.
- **Do NOT clear other entries.** Other watchlists' cached results are preserved.

### 5. "Last scanned X ago" indicator on each card

Each card displays "Last scanned `<relative time>`" beneath the symbol/price header.

Implementation:

- Small pure helper `formatRelativeTime(date)`, colocated with the page initially.
- **No `dayjs` / `luxon` / `moment` dependency added.** Use native `Intl.DateTimeFormat` for absolute dates and inline math for relative ages.
- Promote to `web/src/lib/relativeTime.js` if reused elsewhere in this commit (e.g., if OTA-631 also wants this helper — verify by checking whether D1's T2 commit colocated a separate copy; if so, reconcile into shared `web/src/lib/`).

Relative-time format (SharePoint convention):

| Age | Display |
| --- | --- |
| < 60s | `just now` |
| < 60 min | `12 minutes ago` |
| < 24 h | `3 hours ago` |
| < 7 days | `2 days ago` |
| ≥ 7 days (current year) | `May 3` |
| ≥ 1 year ago | `May 3, 2025` |

### 6. Re-render cards on minute boundary (optional polish)

If trivial, set up a 60s interval to re-render so "12 minutes ago" updates to "13 minutes ago" without requiring user action. Use `useEffect` cleanup to prevent leaks. If the interval introduces complexity, defer — the displayed time updates on any user interaction anyway.

---

## Acceptance criteria

1. **Cache structure:** `localStorage['ota_scan_results']` is a map keyed by `sourceId`. Verify by inspecting localStorage in dev tools.
2. **Multi-watchlist preservation:** Scan watchlist A → switch to B and scan → switch back to A → A's results reappear with no network call (verify in dev tools Network tab).
3. **Initial auto-select does not wipe:** Open Security Strategies page fresh → page auto-selects a default source → if cache had a prior entry for that source, results hydrate. (Preserves OTA-534's fix.)
4. **Manual switch does not auto-scan:** Switch to a watchlist with no cache entry → empty state displayed, no network calls fired.
5. **Card indicator:** Every card shows "Last scanned X ago" beneath the symbol/price header. Format follows the SharePoint table above.
6. **Version mismatch handling:** Manually edit one cache entry's `version` to a different value → reload page → that entry is treated as a miss; other entries are preserved.
7. **Legacy cache migration:** Manually replace `localStorage['ota_scan_results']` with the old single-object form → reload page → cache is discarded cleanly with no console errors; empty state displayed.
8. **No new dependencies:** `package.json` diff shows no new packages added.

---

## Out of scope

- Server-side scan persistence (OTA-624 territory — that's T1 of this same deployment).
- TTL or auto-purge of cached entries (manual cleanup acceptable; future Story if volume warrants).
- "Scan all watchlists" bulk action.
- Visual cache-status indicator beyond the per-card "Last scanned" text.

---

## Verification steps (run before commit)

1. **Manual smoke (dev frontend):**
   - Open Security Strategies page → scan watchlist A → results render with "just now" indicator.
   - Switch to watchlist B → empty state (or B's cached results if any).
   - Scan watchlist B → results render with "just now".
   - Switch back to A → A's results reappear; "Last scanned" shows the actual elapsed time (e.g., "2 minutes ago").
   - Network tab confirms NO new request fired when switching back to A.
2. **Refresh page** while on watchlist A → A's results still hydrate from cache. Switch to B → B's results hydrate from cache. Both indicators reflect the original `scanned_at`.
3. **Version bump test:** edit `formatRelativeTime`'s implementation or the cache version constant → reload → all entries treated as misses (no stale renders).
4. **Legacy cache test:** paste the old single-object shape into localStorage → reload → page renders empty state without throwing.
5. **No console errors** on any of the above flows.
6. **`var(--bg2)`** not used on the "Last scanned" text. Verify with grep on the diff.
7. **No new package dependencies** introduced. `git diff package.json package-lock.json` shows no additions.

If any verification fails, stop and report.

---

## Commit instruction

**I have been instructed to commit. Do you approve? (yes / no)**

One commit covers OTA-629.

## Push instruction

**DO NOT push. Single push for Deployment 3 will be coordinated by Don after all D3 terminals (T1, T2, T3) report commit.**

## Coordination footer

**Independent — no downstream dependency.** This terminal closes after committing.

## Commit message template

```
OTA-629 feat: per-watchlist scan cache; "Last scanned X ago" indicator on cards
```

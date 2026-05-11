# OTA-596: Show security name after signal pill on Security Strategies cards

Implement OTA-596.

## Context

On the Security Strategies (scan) page, each card header currently shows only the ticker, the signal pill (BULLISH / MIXED / BEARISH), and the NEW badge when applicable. For ETFs especially (IEMG, VWO, IJR, AGG, VXUS, etc.), the symbol alone doesn't convey what the security is. Adding the name reduces lookup friction during scanning.

## Change

Render the security name immediately after the signal pill in the card header, using smaller, muted type. Truncate with ellipsis if the name doesn't fit on one line — never wrap. When truncated, show a tooltip with the full name on hover.

## Visual spec

- **Position:** after the signal pill (and after the NEW badge if present), on the same row as the symbol.
- **Typography:** 10px, weight 400, color `var(--muted)`, monospace (consistent with UI-GUIDANCE Part 5).
- **Truncation:** `white-space: nowrap; overflow: hidden; text-overflow: ellipsis;`.
- **Container behavior:** `flex: 1; min-width: 0;` — the name shrinks first; the symbol and signal pill never shrink or get pushed off the row.
- **Tooltip on hover (only when truncated):** match the existing UI-GUIDANCE Part 8 tooltip style — `var(--bg3)` background, `1px var(--border)`, 9px normal, 3px 8px padding. When the name fits without truncation, no tooltip shows.

## Behavior examples

- `IEMG  BULLISH  iShares Core MSCI Emerging Markets ETF`
- `GLD  MIXED  SPDR Gold Shares`
- `VXUS  BULLISH  Vanguard Total International Stock Index F…` (truncated; hover reveals the full name)

## Data source

The security name should come from the existing scan API response. Verify whether the `/security-strategies` scan payload already includes a name/description field per symbol. If not, add it: use the `description` field already returned by the Schwab quote so we don't introduce a new lookup. If the name is null/empty, render the header exactly as it does today (no empty-string artifact, no extra whitespace, no tooltip).

## Acceptance criteria

1. Each Security Strategies card shows the security name immediately after the signal pill, in 10px muted monospace.
2. When the name is too long to fit, it truncates with an ellipsis on the same line — no wrapping, ever.
3. The ticker and signal pill never shrink or get clipped; only the name container shrinks.
4. Hovering a truncated name shows a tooltip with the full untruncated name, styled per UI-GUIDANCE Part 8 tooltip spec. Names that fit show no tooltip.
5. Cards without a name available render the header exactly as before — no empty span, no stray whitespace, no tooltip.
6. Cards at the 280px minimum width still render the ticker + pill cleanly with the name truncated.

## Files likely touched

- The Security Strategies card component (within `pages/SecurityStrategies.jsx` or its card subcomponent — verify the actual location)
- Backend scan endpoint serializer if `description` isn't already in the payload

## Out of scope

- Showing names anywhere besides the Security Strategies cards (Trades QuoteBar, Positions, etc. — handled separately if/when needed).

## Workflow

1. Locate the Security Strategies card component and confirm the current header structure.
2. Inspect the `/security-strategies` response shape to determine whether `description` is already present; if not, plumb it through from the Schwab quote.
3. Implement the header change with the truncation + tooltip behavior per the visual spec.
4. Verify against acceptance criteria at multiple card widths (including 280px minimum).
5. When complete, move OTA-596 to "In Review" and post a brief summary comment with files changed.

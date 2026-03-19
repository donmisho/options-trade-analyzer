# Claude Code Build Prompt: Options Decision Terminal v4.0

> **How to use this file:**
> Open Claude Code in your project root, paste this entire document, and press enter.
> Claude Code will read your live files before writing anything.

---

## CONTEXT & CONSTRAINTS

You are building a major frontend overhaul for the Options Analyzer application.
This is a React + Vite frontend located at `web/` talking to a FastAPI backend at `app/`.

Before writing a single line of code, read every file listed below in full.
Do not assume field names, component structure, or API shapes — read the actual files.

```
cat web/src/App.jsx
cat web/src/components/Header.jsx
cat web/src/components/Layout.jsx
cat web/src/context/AppContext.jsx
cat web/src/pages/VerticalsPage.jsx
cat web/src/pages/LongCallsPage.jsx
cat web/src/components/AskClaudePanel.jsx
cat web/src/components/FormulaBreakdownPanel.jsx
cat web/src/api/client.js
cat app/analysis/vertical_engine.py
cat app/analysis/long_call_engine.py
cat app/api/analysis_routes.py
```

Do not proceed until all 12 files have been read.

---

## ARCHITECTURAL GOAL

Replace the per-strategy pages (`VerticalsPage`, `LongCallsPage`, `NakedOptionsPage`) with
a single reusable shell called `OptionsTerminal`. Each strategy is defined as a config
object. The terminal reads the config and renders accordingly — it has zero hardcoded
knowledge of any strategy.

This is the "plugin shell" pattern. The terminal is the stage. Strategies are the actors.

### Why this matters for future-proofing

The active strategy is stored as a single string in `App.jsx` state (e.g. `"verticals"`).
Today, tabs in `Header.jsx` set that string. Tomorrow, a dropdown could set it. A URL param
could set it. A mobile nav could set it. The terminal never changes — only the mechanism
that writes to `activeStrategy` changes. This is the correct separation of concerns.

### The full file structure you are creating

```
web/src/
├── App.jsx                          ← UPDATE: add activeStrategy state, wire terminal
├── components/
│   └── Header.jsx                   ← UPDATE: dynamic tabs from config registry
├── pages/
│   └── OptionsTerminal.jsx          ← NEW: the reusable shell (4-stage layout)
└── strategy-configs/
    ├── index.js                     ← NEW: registry mapping key → config
    ├── verticals.config.js          ← NEW: vertical spreads config
    └── long-calls.config.js         ← NEW: long calls config
```

The old page files (`VerticalsPage.jsx`, `LongCallsPage.jsx`) are NOT deleted.
Comment out their imports in `App.jsx` but leave the files in place.

---

## STEP 1 — Create the Strategy Config Registry

**Create:** `web/src/strategy-configs/index.js`

This file exports one object: `STRATEGY_CONFIGS`. It maps strategy keys to config objects.

Each config object has this exact shape. Read it carefully — the terminal will depend
on every field being present:

```js
{
  // ── Identity ──────────────────────────────────────────────────────────
  key: string,              // "verticals" | "long_calls" — matches object key
  label: string,            // "Vertical Spreads" — used in grid header
  tabLabel: string,         // "Verticals" — used in Header tabs

  // ── API ───────────────────────────────────────────────────────────────
  apiEndpoint: string,      // "/api/v1/analyze/vertical"
  // Builds the POST body sent to the API. Read the existing page to find exact params.
  buildApiParams: (symbol, userConfig) => object,

  // ── Response parsing ──────────────────────────────────────────────────
  // Tell the terminal which array key holds the trades in the API response
  tradesKey: string,        // "spreads" | "calls"

  // ── Grid columns ──────────────────────────────────────────────────────
  columns: [
    {
      key: string,                          // field name on trade object, or "badge" / "health"
      label: string,                        // column header text
      width: number,                        // px
      align: "left" | "right" | "center",
      // Receives (value, trade) — return a string or JSX
      format: (value, trade) => any,
    }
  ],

  // ── Type badge ────────────────────────────────────────────────────────
  // Returns display label + colors for the strategy type badge in the grid
  getBadge: (trade) => { label: string, color: string, bg: string },

  // ── Health pips ───────────────────────────────────────────────────────
  // 3 colored dots shown in each row. Define thresholds per strategy.
  getHealthPips: (trade) => [
    { color: string },   // pip 1
    { color: string },   // pip 2
    { color: string },   // pip 3
  ],

  // ── Payoff diagram ────────────────────────────────────────────────────
  payoffType: "spread" | "single_leg",
  // If "spread": return array of { price, pnl } points for Recharts AreaChart
  // If "single_leg": set to null
  payoffFn: ((trade, currentPrice) => Array) | null,
}
```

---

### Config: `web/src/strategy-configs/verticals.config.js`

Read `VerticalsPage.jsx` and `app/analysis/vertical_engine.py` to get exact field names
and API param structure before writing this config. Do not guess field names.

```
key: "verticals"
label: "Vertical Spreads"
tabLabel: "Verticals"
apiEndpoint: "/api/v1/analyze/vertical"  (verify in analysis_routes.py)
tradesKey: "spreads"

columns:
  #         | row index        | 30px  | center
  type      | badge            | 100px | center  (uses getBadge)
  spread    | buy/sell strikes | 90px  | center  (format: "520/530")
  exp       | expiration       | 70px  | center  (format: "03-20")
  net       | net_cost         | 65px  | right   (format: 2 decimal, NO currency symbol)
  rr        | reward_risk_ratio| 55px  | right   (format: "1.94")
  prob      | prob_of_profit   | 55px  | right   (format: "62%")
  score     | composite_score  | 80px  | center  (color bar, 4 decimal label)
  health    | health pips      | 70px  | center  (uses getHealthPips)

getBadge:
  bull_call → { "BULL CALL", color: "#20C997", bg: "#20C99720" }
  bear_put  → { "BEAR PUT",  color: "#FF9E43", bg: "#FF9E4320" }
  bear_call → { "BEAR CALL", color: "#8A70FF", bg: "#8A70FF20" }
  bull_put  → { "BULL PUT",  color: "#22D3EE", bg: "#22D3EE20" }

getHealthPips:
  pip 1 — R:R:    ≥ 1.5 → #20C997   ≥ 1.0 → #FF9E43   else → #FF5A5A
  pip 2 — Prob:   ≥ 0.55 → #20C997  ≥ 0.45 → #FF9E43  else → #FF5A5A
  pip 3 — Score:  ≥ 0.65 → #20C997  ≥ 0.45 → #FF9E43  else → #FF5A5A

payoffType: "spread"
payoffFn: vertical spread trapezoid
  x range: currentPrice ± 12%, 60 points
  bull_call / bull_put (long direction):
    price < buy_strike:               pnl = -(net_cost * 100)
    buy_strike ≤ price ≤ sell_strike: pnl = linear ramp from -max_loss to +max_profit
    price > sell_strike:              pnl = max_profit * 100
  bear_put / bear_call (short direction): mirror — profit below, loss above
```

---

### Config: `web/src/strategy-configs/long-calls.config.js`

Read `LongCallsPage.jsx` and `app/analysis/long_call_engine.py` before writing.

```
key: "long_calls"
label: "Long Calls"
tabLabel: "Long Calls"
apiEndpoint: "/api/v1/analyze/long-calls"  (verify in analysis_routes.py)
tradesKey: "calls"

columns:
  #         | row index        | 30px  | center
  strike    | strike price     | 70px  | right   (integer display)
  exp       | expiration       | 70px  | center
  delta     | delta            | 65px  | right   (4 decimal)
  iv        | iv               | 65px  | right   (format as "23.4%")
  premium   | mid_price        | 70px  | right   (2 decimal, NO currency symbol)
  breakeven | breakeven        | 85px  | right   (2 decimal)
  runway    | theta_runway     | 80px  | right   (integer, label "days")
  score     | composite_score  | 80px  | center  (color bar, 4 decimal label)
  health    | health pips      | 70px  | center

getBadge: always { "LONG CALL", color: "#20C997", bg: "#20C99720" }

getHealthPips: read LongCallsPage to find which fields it uses for scoring,
  then set thresholds that make sense for calls (delta, IV, runway)

payoffType: "single_leg"
payoffFn: null
```

---

## STEP 2 — Build OptionsTerminal.jsx

**Create:** `web/src/pages/OptionsTerminal.jsx`

This is the shell. It receives `{ activeStrategy }` as a prop.
It looks up `const config = STRATEGY_CONFIGS[activeStrategy]`.
It never references `"verticals"` or `"long_calls"` by name internally.

### State

```js
const [symbol, setSymbol] = useState("QQQ")
const [inputSymbol, setInputSymbol] = useState("QQQ")
const [trades, setTrades] = useState([])
const [underlyingPrice, setUnderlyingPrice] = useState(0)
const [candles, setCandles] = useState([])
const [loading, setLoading] = useState(false)
const [error, setError] = useState(null)
const [selectedTradeId, setSelectedTradeId] = useState(null)
const [drawerTrade, setDrawerTrade] = useState(null)
const [drawerOpen, setDrawerOpen] = useState(false)
const [userConfig, setUserConfig] = useState({})
```

When `activeStrategy` changes: reset `trades`, `selectedTradeId`, `drawerOpen` to defaults,
then run `runAnalysis()` with the new config automatically.

### runAnalysis function

```js
async function runAnalysis(sym = symbol) {
  setLoading(true)
  setError(null)
  try {
    const params = config.buildApiParams(sym, userConfig)
    const response = await apiPost(config.apiEndpoint, params)  // use existing client.js pattern
    const tradeList = response[config.tradesKey] || []
    setTrades(tradeList)
    setUnderlyingPrice(response.underlying_price || 0)
    setCandles(generateCandles(response.underlying_price))
  } catch (err) {
    setError(err.message)
    setTrades([])
  } finally {
    setLoading(false)
  }
}
```

Copy `generateCandles()` from `VerticalsPage.jsx` — do not rewrite it.

---

### STAGE 0 — Header & Chart

#### Navigation Bar

```
[QQQ pill]   [_________ input _________] [Analyze]   [spinner if loading]
```

- Symbol pill: monospace, large, `#E8EDF3` text on `#1A1E23` background, `#2C313B` border
- Input: controlled, onSubmit calls `setSymbol(inputSymbol)` then `runAnalysis(inputSymbol)`
- Analyze button: `#8A70FF` background, black text, monospace

#### Market Data Ribbon

Single dense row. 8 fields. No currency symbols. All separated by thin `#2C313B` dividers.

```
PRICE      CHG      CHG%     DAY RANGE     52W RANGE     VOLUME    REL VOL    DTE SIGNAL
607.69   +1.23    +0.20%   604.10–610.33  512–650.00    1.2M      1.1x Vol   ◆ Mixed
```

Derive from `underlyingPrice` and `candles` if the API doesn't return a quote object.
Read `client.js` — if `getQuote()` exists, call it in parallel with `runAnalysis()`.
If a field can't be computed, display `—`.

Color rules:
- Positive change: `#20C997`
- Negative change: `#FF9E43`
- Neutral / unknown: `#8A919E`

#### Signal Banner

28px tall slim bar. Full width. Compute SMA values from `candles`:

```js
const sma = (n) => candles.slice(-n).reduce((s,c) => s + c.close, 0) / n
const sma8  = sma(8)
const sma21 = sma(21)
const sma50 = sma(50)
const price = candles[candles.length - 1]?.close || underlyingPrice
```

Signal logic:
```
price > sma8 > sma21 > sma50  → "◆ Bullish Alignment — Price above all 3 SMAs"
  bg: #20C997, text: #000000
sma8 < sma21                  → "◆ Bearish Signal — Short-term weakness"
  bg: #FF9E43, text: #000000
else                           → "◆ Mixed — No directional confirmation"
  bg: #2C313B, text: #8A919E
```

#### Main Candlestick Chart

Recharts `ComposedChart`, height 200px, full width.

Copy `generateCandles()` from `VerticalsPage.jsx` exactly. Do not alter its logic.

Custom candle shape using Recharts `customized` prop on a `Bar`:

```
Each candle renders two SVG rects:
  Body:  x=centerX-3, y=Math.min(open,close), width=6, height=Math.abs(close-open)
  Wick:  x=centerX-0.5, y=low, width=1, height=high-low (in price-to-pixel coords)
Green (close > open): fill #20C99730, stroke #20C997
Red   (close ≤ open): fill #FF5A5A30, stroke #FF5A5A
```

SMA lines as Recharts `Line` components (no dots):
```
sma8:  stroke #22D3EE, strokeWidth 1.5
sma21: stroke #FB923C, strokeWidth 1.5
sma50: stroke #FB7185, strokeWidth 1.5
```

`ReferenceLine` at current price: stroke `#8A70FF`, strokeDasharray `"4 4"`

Chart config:
```
YAxis: right side, width 55, tick color #55606D, grid stroke #1E2330
XAxis: bottom, abbreviated date labels, tick color #55606D
Tooltip: dark background #1A1E23, border #2C313B, show O/H/L/C
Margin: { top: 8, right: 60, bottom: 4, left: 0 }
```

---

### STAGE 1 — Master Grid

Header row:
```
Left:  "{symbol} {config.label}  ·  {trades.length} results"
Right: "Click a row to see scoring breakdown →" (muted)
```

Column headers: render dynamically from `config.columns`.

Trade rows:
- Render one `<tr>` per trade
- Each cell: `config.columns[i].format(trade[config.columns[i].key], trade)`
- Special keys `"badge"` and `"health"` render `getBadge(trade)` and `getHealthPips(trade)`
- Score column: render as a color bar (replicate the score bar from `ResultsTable.jsx` —
  read that component first)
- Row click: `setSelectedTradeId(trade.id ?? idx)` — toggle off if already selected
- Selected row style: `borderLeft: "3px solid #8A70FF"`, `background: "#8A70FF08"`

After the selected row's `<tr>`, conditionally render the Stage 2 expansion `<tr>`.

---

### STAGE 2 — Inline Expansion

Renders as a full-width `<tr>` → single `<td colSpan={config.columns.length}>`.

```
background: #1A1E23
borderTop: 2px solid #8A70FF
padding: 16px
```

Two-column layout: 58% left | 42% right, gap 16px.

#### Left panel: Math Matrix

Read `FormulaBreakdownPanel.jsx` in full before writing this. Replicate its 5-metric
breakdown as a compact inline table. Do NOT import or reuse `FormulaBreakdownPanel` —
rebuild it here as a simplified version without the outer panel chrome.

Each metric row:
```
[Name + weight badge]  [formula text]  [math text]  [bar]  [contribution]
```

Use the same field names for scores that `FormulaBreakdownPanel` uses.
Show composite total at bottom, highlighted in `#8A70FF`.

If a score field is missing from the trade object, show `—` rather than crashing.

#### Right panel: Payoff Diagram

Check `config.payoffType`:

**If `"single_leg"`:** render a muted placeholder:
```
background: #13161A
border: 1px dashed #2C313B
text: "Payoff diagram available for spread strategies" (#55606D, centered)
height: 160px
```

**If `"spread"`:** render `Recharts AreaChart` using `config.payoffFn(trade, underlyingPrice)`.

Chart specs:
```
height: 160px
Area: dataKey="pnl"
  fill: url(#payoffGradient)
  stroke: #8A70FF, strokeWidth 2
Gradient definition:
  above 0: #20C99720
  below 0: #FF5A5A20
ReferenceLine y=0:         stroke #2C313B, strokeDasharray "3 3"
ReferenceLine x=currentP:  stroke #8A70FF40, strokeDasharray "3 3"
XAxis: show tick at buy_strike, sell_strike, currentPrice only
YAxis: right side, small font, P&L labels
```

#### Bottom of expansion: CTA

Full-width violet button:
```
background: #8A70FF
text: "✦ View Full Claude Thesis"   (monospace, bold, white)
height: 40px
onClick: setDrawerTrade(selectedTrade), setDrawerOpen(true)
```

---

### STAGE 3 — Side Drawer

Reuse the existing `AskClaudePanel` component. Do not rebuild it.

```jsx
<>
  {drawerOpen && (
    <div
      onClick={() => setDrawerOpen(false)}
      style={{
        position: "fixed", inset: 0,
        background: "#00000060",
        backdropFilter: "blur(2px)",
        zIndex: 40,
      }}
    />
  )}
  <AskClaudePanel
    open={drawerOpen}
    onClose={() => setDrawerOpen(false)}
    trade={drawerTrade}
    smaData={getSmaData()}
    smaPeriods={{ short: 8, mid: 21, long: 50 }}
  />
</>
```

`getSmaData()`: extract `{ price, smaShort, smaMid, smaLong }` from candles — same as in `VerticalsPage.jsx`. Copy that function exactly.

---

## STEP 3 — Update App.jsx

Add `activeStrategy` state, defaulting to `"verticals"`:
```js
const [activeStrategy, setActiveStrategy] = useState("verticals")
```

Pass `activeStrategy` and `setActiveStrategy` as props to `Header`.

Replace the routes that previously rendered `VerticalsPage` and `LongCallsPage` with:
```jsx
<OptionsTerminal activeStrategy={activeStrategy} />
```

Keep all other routes unchanged (auth, favorites, directional, settings).

Comment out — do not delete — the old page imports:
```js
// import VerticalsPage from "./pages/VerticalsPage"
// import LongCallsPage from "./pages/LongCallsPage"
```

---

## STEP 4 — Update Header.jsx

Import the config registry:
```js
import { STRATEGY_CONFIGS } from "../strategy-configs/index"
```

Replace hardcoded tab buttons with a dynamic render:
```jsx
{Object.values(STRATEGY_CONFIGS).map(cfg => (
  <button
    key={cfg.key}
    onClick={() => setActiveStrategy(cfg.key)}
    className={activeStrategy === cfg.key ? "tab-active" : "tab"}
  >
    {cfg.tabLabel}
  </button>
))}
```

Match the existing tab styling exactly — read `Header.jsx` first.
`setActiveStrategy` is received as a prop from `App.jsx`.

---

## VISUAL THEME

Apply consistently across all new files:

```
Colors:
  Background:       #13161A
  Surface:          #1A1E23
  Border:           #2C313B
  Bullish/Profit:   #20C997
  Bearish/Risk:     #FF9E43
  AI/Action:        #8A70FF
  Text primary:     #E8EDF3
  Text secondary:   #8A919E
  Text muted:       #55606D
  Red/Stop:         #FF5A5A
  Cyan (SMA 8):     #22D3EE
  Orange (SMA 21):  #FB923C
  Rose (SMA 50):    #FB7185

Typography:
  Monospace stack: 'IBM Plex Mono', 'Fira Code', 'Consolas', monospace
  Use monospace for: all prices, strikes, scores, percentages, labels

Formatting rules (NO EXCEPTIONS):
  NO currency symbols anywhere (602.98 not $602.98)
  Prices and financial values: 2 decimal places
  Score values: 4 decimal places (0.7615 not 0.76)
  Greeks: 4 decimal places (0.4823)
  Probability: integer percent suffix (62% not 0.62)
  Volume: abbreviated (1.2M, 45.3K)
  Strike prices in grid: integer (520 not 520.00)
  R:R: 2 decimals (1.94)
```

---

## JSON SCHEMAS

These are the exact data shapes the configs and terminal must handle.
Read the actual API route files to verify these match — if there is a discrepancy,
the live file wins.

### API Response — Verticals
```json
{
  "spreads": [
    {
      "spread_type": "bull_call",
      "buy_strike": 520,
      "sell_strike": 530,
      "expiration": "2026-03-20",
      "net_cost": 3.41,
      "max_profit": 6.59,
      "max_loss": 3.41,
      "reward_risk_ratio": 1.93,
      "prob_of_profit": 0.62,
      "composite_score": 0.7615,
      "long_delta": 0.55,
      "short_delta": 0.42,
      "net_theta": -0.0180,
      "long_volume": 245,
      "short_volume": 312,
      "long_oi": 1820,
      "short_oi": 2450,
      "ev_score": 0.82,
      "rr_score": 0.71,
      "prob_score": 0.68,
      "liq_score": 0.89,
      "theta_score": 0.55
    }
  ],
  "underlying_price": 607.69,
  "total_valid": 4
}
```

### API Response — Long Calls
```json
{
  "calls": [
    {
      "strike": 520,
      "expiration": "2026-03-20",
      "mid_price": 3.42,
      "delta": 0.4823,
      "iv": 0.2341,
      "theta": -0.0180,
      "breakeven": 523.42,
      "theta_runway": 190.11,
      "composite_score": 0.7250,
      "rr_score": 0.71,
      "delta_score": 0.9200,
      "iv_score": 0.6500,
      "theta_score": 0.5500,
      "liq_score": 0.7800
    }
  ],
  "underlying_price": 607.69,
  "total_valid": 8
}
```

### Claude Evaluation Request (sent to AskClaudePanel)
```json
{
  "symbol": "QQQ",
  "strategy_type": "vertical_spread",
  "spread_type": "bull_call",
  "buy_strike": 520,
  "sell_strike": 530,
  "expiration": "2026-03-20",
  "net_cost": 3.41,
  "max_profit": 6.59,
  "reward_risk_ratio": 1.93,
  "prob_of_profit": 0.62,
  "composite_score": 0.7615,
  "underlying_price": 607.69,
  "sma_8": 604.78,
  "sma_21": 606.20,
  "sma_50": 608.25,
  "ma_alignment": "Bearish - price below SMA 50"
}
```

---

## DELIVERY ORDER

Build and confirm each file before moving to the next.
After each file, print: `✓ [filename] written`

```
1.  web/src/strategy-configs/index.js
2.  web/src/strategy-configs/verticals.config.js
3.  web/src/strategy-configs/long-calls.config.js
4.  web/src/pages/OptionsTerminal.jsx
5.  web/src/App.jsx  (update)
6.  web/src/components/Header.jsx  (update)
```

After all 6 files are written, run:
```bash
cd web && npm run build
```

Fix all build errors before proceeding to the documentation updates.
Report any field name assumptions you had to make.

---

## FINAL STEP — Update Documentation

After the build is clean, update both documentation files.

### Update `architecture-plan.md`

Add a new section after the existing content:

```markdown
---

## Phase 2.7 — Options Decision Terminal (Frontend Overhaul)

### What Changed

The per-strategy pages (VerticalsPage, LongCallsPage) have been replaced by a single
reusable shell: `OptionsTerminal.jsx`. Each strategy is defined as a config object in
`web/src/strategy-configs/`. The terminal reads the config and renders accordingly.

### New Files

| File | Purpose |
|------|---------|
| `web/src/pages/OptionsTerminal.jsx` | The reusable 4-stage analysis shell |
| `web/src/strategy-configs/index.js` | Strategy registry — maps key → config object |
| `web/src/strategy-configs/verticals.config.js` | Vertical spreads config |
| `web/src/strategy-configs/long-calls.config.js` | Long calls config |

### The Plugin Pattern

To add a new strategy (straddles, iron condors, etc.):
1. Create `web/src/strategy-configs/your-strategy.config.js`
2. Register it in `strategy-configs/index.js`
3. The tab appears in Header automatically. The terminal renders it automatically.
   No changes to OptionsTerminal.jsx or Header.jsx required.

### Strategy Config Shape

Each config answers 5 questions for the terminal:
- **Identity**: label, tabLabel, key
- **API**: endpoint, how to build params, which response key holds trades
- **Grid**: column definitions with format functions
- **Badges & Health**: how to render type badge and 3-pip health indicators
- **Payoff**: payoffType ("spread" | "single_leg") and optional payoffFn

### Active Strategy State

`activeStrategy` string lives in `App.jsx`. Today it is set by tabs in `Header.jsx`.
To change the navigation mechanism in the future (dropdown, URL param, mobile nav),
only `Header.jsx` changes. `OptionsTerminal.jsx` is unaffected.

### Terminal Stages

- **Stage 0**: Ticker nav, market data ribbon, signal banner, candlestick chart with SMA 8/21/50
- **Stage 1**: Master grid — ranked trades, dynamic columns from config
- **Stage 2**: Inline expansion — math matrix + payoff diagram (hidden for single-leg strategies)
- **Stage 3**: Side drawer — AskClaudePanel for AI deep-dive (future: TradeAgentPanel)

### Deprecation

`VerticalsPage.jsx` and `LongCallsPage.jsx` are retained but commented out of routing.
They serve as reference implementations. Remove after one stable release cycle.
```

---

### Update `CLAUDE.md`

Replace the existing Frontend Structure section with:

```markdown
### Frontend Structure

```
web/src/
├── App.jsx                          # Routes + activeStrategy state
├── main.jsx                         # React root
├── context/
│   └── AppContext.jsx               # Shared: activeSymbol, watchlist, favorites, prices
├── api/
│   └── client.js                    # API client (getQuote, analyzeVerticals, etc.)
├── strategy-configs/                # Strategy plugin system
│   ├── index.js                     # Registry: maps key → config object
│   ├── verticals.config.js          # Vertical spreads
│   └── long-calls.config.js         # Long calls
├── components/
│   ├── Layout.jsx                   # Header + Watchlist + <Outlet>
│   ├── Header.jsx                   # Logo, dynamic strategy tabs, Schwab status
│   ├── Watchlist.jsx                # Sidebar with live prices
│   ├── QuoteBar.jsx                 # Active symbol price + 52w range
│   ├── ResultsTable.jsx             # Legacy — superseded by OptionsTerminal grid
│   ├── ConfigDrawer.jsx             # Settings slideout
│   ├── FormulaBreakdownPanel.jsx    # Score formula transparency panel
│   ├── AskClaudePanel.jsx           # AI trade evaluation drawer
│   └── ...                          # ScoreBar, Toast, SymbolInput, etc.
└── pages/
    ├── OptionsTerminal.jsx          # PRIMARY: reusable 4-stage analysis shell
    ├── VerticalsPage.jsx            # DEPRECATED: retained for reference
    ├── LongCallsPage.jsx            # DEPRECATED: retained for reference
    ├── DirectionalPage.jsx          # Directional momentum (not yet migrated)
    └── FavoritesPage.jsx            # Saved trades
```

**State management**: `activeStrategy` (string) lives in `App.jsx` and is passed as a
prop to `Header` (which sets it) and `OptionsTerminal` (which reads it). This decouples
the navigation mechanism from the terminal rendering.

**Adding a new strategy**: Create a config file in `strategy-configs/`, register it in
`index.js`. No other files need to change.
```

Also add to the **Adding a New Analysis Engine** pattern section:

```markdown
### Adding a New Analysis Engine (Updated Pattern)

With the OptionsTerminal architecture, the frontend steps have changed:

1. Create `app/analysis/your_engine.py`
2. Add route in `app/api/analysis_routes.py`
3. Add frontend call in `web/src/api/client.js`
4. **Create `web/src/strategy-configs/your-strategy.config.js`** (not a full page)
5. **Register in `web/src/strategy-configs/index.js`**
6. Tab and terminal rendering happen automatically

No new page file needed. No routing changes needed.
```

---

After updating both documentation files, print:
```
✓ architecture-plan.md updated
✓ CLAUDE.md updated
BUILD COMPLETE
```

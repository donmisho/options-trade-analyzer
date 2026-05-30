# Phase 1a Data Cleanup Log

**Run at:** 2026-05-18 23:37:25 UTC
**Database:** options-analyzer-sql-cus.database.windows.net/options-analyzer-db

## Actions

- INSERT symbol_reference: $DJI (INDEX)
- INSERT symbol_reference: $DJIA (INDEX)
- INSERT symbol_reference: $INX (INDEX)
- INSERT symbol_reference: $NDX (INDEX)
- INSERT symbol_reference: $RUT (INDEX)
- INSERT symbol_reference: $SPX (INDEX)
- INSERT symbol_reference: $VIX (INDEX)
- INSERT symbol_reference: AGG (ETF)
- INSERT symbol_reference: GLD (ETF)
- INSERT symbol_reference: IEFA (ETF)
- INSERT symbol_reference: IEMG (ETF)
- INSERT symbol_reference: IJH (ETF)
- INSERT symbol_reference: IJR (ETF)
- INSERT symbol_reference: IVV (ETF)
- INSERT symbol_reference: IWF (ETF)
- INSERT symbol_reference: QUAL (ETF)
- INSERT symbol_reference: VB (ETF)
- INSERT symbol_reference: VEA (ETF)
- INSERT symbol_reference: VIG (ETF)
- INSERT symbol_reference: VO (ETF)
- INSERT symbol_reference: VOO (ETF)
- INSERT symbol_reference: VTI (ETF)
- INSERT symbol_reference: VTV (ETF)
- INSERT symbol_reference: VUG (ETF)
- INSERT symbol_reference: VWO (ETF)
- INSERT symbol_reference: VXUS (ETF)
- INSERT symbol_reference: TSLA (STOCK)
- INSERT symbol_reference: WDC (STOCK)
- INSERT symbol_reference: WMT (STOCK)
- INSERT symbol_reference: WULF (STOCK)
- INSERT symbol_reference: DJI (INDEX)
- INSERT symbol_reference: IVM (ETF)
- INSERT symbol_reference: XYZNOTAREAL (TEST)
- Symbols: 33 inserted, 0 already existed
- UPDATE watchlists.user_id: 2 rows fixed (6232a881-23e9-4954-8ed0-6303ea7d188 -> 6232a881-23e9-4954-8ed0-6303ea7fd188)
- UPDATE trade_candidates.user_id: 334 rows fixed (6232a881-23e9-4954-8ed0-6303ea7d188 -> 6232a881-23e9-4954-8ed0-6303ea7fd188)
- UPDATE positions.user_id: 13 rows fixed (6232a881-23e9-4954-8ed0-6303ea7d188 -> 6232a881-23e9-4954-8ed0-6303ea7fd188)
- DELETE watchlist_symbols (children of test-user watchlists): 0 rows
- DELETE watchlists (test user 00000000-0000-0000-0000-000000000001): 1 rows
- DELETE user_watchlist (dev-user): 9 rows
- DELETE user_watchlist (test user): 6 rows
- UPDATE agent_run_log.market_snapshot: 7 rows set to NULL
- VERIFY: Remaining symbol orphans across all tables: 0
- VERIFY: watchlists.user_id orphans remaining: 0
- VERIFY: trade_candidates.user_id orphans remaining: 0
- VERIFY: positions.user_id orphans remaining: 0
- VERIFY: watchlists.user_id orphans remaining: 0
- VERIFY: agent_run_log.market_snapshot invalid JSON remaining: 0
- VERIFY: user_watchlist.user_id orphans remaining: 0

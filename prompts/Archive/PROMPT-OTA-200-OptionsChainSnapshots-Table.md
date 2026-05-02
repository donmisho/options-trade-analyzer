---
allowedTools: [Bash, Read, Write, Edit]
---

# OTA-200 — Create options_chain_snapshots Table in Azure SQL

**Jira:** OTA-200 | Parent: OTA-44 (Data Collection — START NOW)
**Priority:** High | **Labels:** options-domain, requirement
**Run standalone. No dependency on other IN PROGRESS tickets.**

---

## Before You Start

```bash
cat app/models/database.py
cat app/models/session.py
cat app/core/config.py
grep -n "symbol_reference\|positions\|agent_run_log" app/models/database.py
grep -n "get_chain\|options_chain" app/providers/schwab_market_data.py
```

Read all output completely before making any changes.

---

## Goal

Create the `options_chain_snapshots` table in Azure SQL and begin daily collection
for watchlist symbols using the existing Schwab endpoint. This is the data foundation
for backtesting (Phase 3.3.x).

---

## Step 1 — Define the SQLAlchemy Model

In `app/models/database.py`, add the `OptionsChainSnapshot` model:

```python
class OptionsChainSnapshot(Base):
    __tablename__ = "options_chain_snapshots"

    snapshot_id     = Column(UNIQUEIDENTIFIER, primary_key=True, default=uuid.uuid4)
    symbol          = Column(String(20), nullable=False, index=True)
    snapshot_date   = Column(Date, nullable=False, index=True)
    captured_at     = Column(DateTime2, default=func.getutcdate(), nullable=False)
    underlying_price = Column(Float, nullable=False)
    chain_json      = Column(Text, nullable=False)   # full serialized chain from provider
    contract_count  = Column(Integer, nullable=False) # number of contracts in snapshot
    dte_min         = Column(Integer, nullable=True)  # min DTE in snapshot
    dte_max         = Column(Integer, nullable=True)  # max DTE in snapshot
    provider        = Column(String(50), nullable=False, default="schwab")
    
    __table_args__ = (
        UniqueConstraint('symbol', 'snapshot_date', name='uq_chain_snapshot_symbol_date'),
    )
```

**Notes:**
- `chain_json` stores the full options chain as serialized JSON string (same structure
  returned by `provider.get_chain()`). Do NOT normalize into individual rows — that
  comes in a later phase.
- `UniqueConstraint` prevents duplicate daily snapshots per symbol.
- Use Azure SQL compatible types: `UNIQUEIDENTIFIER`, `DateTime2`, `Date`.

---

## Step 2 — Create Alembic Migration (or direct DDL)

Check how existing tables are managed:

```bash
ls app/migrations/ 2>/dev/null || echo "no migrations folder"
grep -n "create_all\|alembic" app/models/session.py app/main.py
```

If the project uses `metadata.create_all()` (common for this project), add the model in
Step 1 and it will be picked up automatically on next startup.

If Alembic is in use, generate a migration:
```bash
cd options-analyzer
.\venv\Scripts\Activate.ps1
alembic revision --autogenerate -m "OTA-200 add options_chain_snapshots table"
alembic upgrade head
```

---

## Step 3 — Create the Daily Snapshot Collection Function

In `app/api/` (or `app/analysis/`), create `chain_collection.py`:

```python
"""
options_chain_snapshots daily collection.
Triggered by the scheduler or on-demand via POST /api/v1/data/collect-chains.
OTA-200
"""

async def collect_chain_snapshot(symbol: str, db_session) -> dict:
    """
    Fetch current options chain for symbol via Schwab provider and write one
    snapshot row. Skips if a snapshot already exists for today.
    
    Returns: { symbol, snapshot_date, contract_count, status: "inserted"|"skipped"|"error" }
    """
    from app.providers.factory import _get_provider
    from app.models.database import OptionsChainSnapshot
    from datetime import date, datetime, timezone
    import json

    today = date.today()
    
    # Skip if already collected today
    existing = await db_session.execute(
        select(OptionsChainSnapshot)
        .where(OptionsChainSnapshot.symbol == symbol)
        .where(OptionsChainSnapshot.snapshot_date == today)
    )
    if existing.scalar_one_or_none():
        return { "symbol": symbol, "snapshot_date": str(today), "status": "skipped" }
    
    # Fetch chain
    provider = _get_provider()
    chain_data = await provider.get_chain(symbol, min_dte=0, max_dte=70, strike_range_pct=20)
    
    contracts = chain_data.get("contracts", [])
    underlying_price = chain_data.get("underlying_price", 0.0)
    
    dtes = [c.get("dte", 0) for c in contracts if c.get("dte") is not None]
    
    snapshot = OptionsChainSnapshot(
        symbol=symbol,
        snapshot_date=today,
        captured_at=datetime.now(timezone.utc),
        underlying_price=underlying_price,
        chain_json=json.dumps(chain_data),
        contract_count=len(contracts),
        dte_min=min(dtes) if dtes else None,
        dte_max=max(dtes) if dtes else None,
        provider="schwab",
    )
    db_session.add(snapshot)
    await db_session.commit()
    
    return {
        "symbol": symbol,
        "snapshot_date": str(today),
        "contract_count": len(contracts),
        "status": "inserted"
    }
```

---

## Step 4 — Add On-Demand Trigger Endpoint

In `app/api/market_routes.py` (or appropriate routes file), add:

```python
@router.post("/api/v1/data/collect-chains")
async def trigger_chain_collection(
    symbols: list[str],
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_write)
):
    """
    On-demand chain snapshot collection. Provide list of symbols.
    Scheduler calls this nightly; manual trigger available for testing.
    """
    from app.analysis.chain_collection import collect_chain_snapshot
    results = []
    for symbol in symbols:
        result = await collect_chain_snapshot(symbol, db)
        results.append(result)
    return { "collected": len([r for r in results if r["status"] == "inserted"]),
             "skipped": len([r for r in results if r["status"] == "skipped"]),
             "errors": len([r for r in results if r["status"] == "error"]),
             "details": results }
```

---

## Step 5 — Verify via Swagger

After server restart:
1. Navigate to `https://127.0.0.1:8000/docs`
2. Call `POST /api/v1/data/collect-chains` with body `["AAPL", "XOM"]`
3. Confirm response shows `status: "inserted"` for both
4. Call again immediately — confirm response shows `status: "skipped"` (idempotent)
5. Check Azure SQL table `options_chain_snapshots` for the two rows

---

## Acceptance Criteria

- [ ] `options_chain_snapshots` table exists in Azure SQL with correct schema
- [ ] `UniqueConstraint` on `(symbol, snapshot_date)` prevents duplicates
- [ ] `collect_chain_snapshot()` function writes one row per symbol per day
- [ ] Second call on same day returns `"skipped"` without error
- [ ] `POST /api/v1/data/collect-chains` endpoint accepts symbol list and returns results
- [ ] `provider = _get_provider()` used — never hardcoded `"schwab"`
- [ ] No data loss on failure (atomic write per symbol)
- [ ] `chain_json` stores full serialized chain data

---

## House Style Rules

- Provider routing: always `_get_provider()`, never hardcode provider name
- Date format in API responses: `mm-dd-yyyy` via `formatDate()` (frontend)
- DB: ISO UTC timestamps

---

## Commit Message

```
OTA-200 Create options_chain_snapshots table and daily collection endpoint
```

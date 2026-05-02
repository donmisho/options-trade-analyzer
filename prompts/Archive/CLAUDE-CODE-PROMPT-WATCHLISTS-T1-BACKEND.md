# Claude Code Prompt — Named Watchlists Backend (T1)
# Tickets: OTA-444 (DB schema) + OTA-445 (API endpoints)
# Terminal: T1 (Backend)
# Run BEFORE T2 (frontend depends on these endpoints)

---

## Step 0 — Read Context

```bash
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
cat claude_context/CLAUDE.md
```

Then read these files to understand the existing patterns:
- `app/routers/` — see how existing routers are structured (auth, routes, error handling)
- `app/db.py` or equivalent — see how DB connections work
- `app/routers/positions_routes.py` — the positions endpoint is the closest pattern to follow
- `app/routers/scan_routes.py` — the Security Strategies scanner endpoint

---

## Step 1 — Database Schema (OTA-444)

Create a SQL migration script and run it against Azure SQL.

```sql
-- Migration: Named Watchlists
-- Ticket: OTA-444

CREATE TABLE watchlists (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    name NVARCHAR(100) NOT NULL,
    user_id NVARCHAR(255) NOT NULL,
    is_default BIT DEFAULT 0,
    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE()
);

CREATE INDEX idx_watchlists_user ON watchlists(user_id);

CREATE TABLE watchlist_symbols (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    watchlist_id UNIQUEIDENTIFIER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol NVARCHAR(20) NOT NULL,
    added_at DATETIME2 DEFAULT GETUTCDATE(),
    CONSTRAINT uq_watchlist_symbol UNIQUE(watchlist_id, symbol)
);

CREATE INDEX idx_watchlist_symbols_watchlist ON watchlist_symbols(watchlist_id);
```

**Connection string:** Use the same Azure SQL connection pattern as the existing `positions` table. Check `app/db.py` or `app/database.py` for the connection string source (likely Key Vault or environment variable).

**Verify:** After running the migration, confirm both tables exist:
```sql
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME IN ('watchlists', 'watchlist_symbols');
```

---

## Step 2 — Backend API Router (OTA-445)

Create `app/routers/watchlist_routes.py` with these endpoints:

### GET /api/v1/watchlists
- Returns all watchlists for the authenticated user
- **Lazy default creation:** If no watchlists exist for this user, create one named "My Watchlist" with `is_default=1` and return it
- Response: `[{id, name, is_default, symbol_count, created_at, updated_at}]`
- `symbol_count` is a computed field (COUNT from watchlist_symbols)

### POST /api/v1/watchlists
- Body: `{name: string}`
- Creates a new watchlist for the authenticated user
- Validate: name is 1-100 chars, not empty
- Response: `{id, name, is_default: false, symbol_count: 0, created_at}`

### PUT /api/v1/watchlists/{watchlist_id}
- Body: `{name: string}`
- Renames the watchlist. Must belong to authenticated user.
- Response: `{id, name, updated_at}`

### DELETE /api/v1/watchlists/{watchlist_id}
- Deletes watchlist and all its symbols (CASCADE)
- **Cannot delete default watchlist** — return 400 with message "Cannot delete default watchlist"
- Must belong to authenticated user
- Response: 204 No Content

### GET /api/v1/watchlists/{watchlist_id}/symbols
- Returns all symbols in the watchlist
- Must belong to authenticated user
- Response: `[{symbol, added_at}]` ordered by `added_at DESC`

### POST /api/v1/watchlists/{watchlist_id}/symbols
- Body: `{symbol: string}`
- Uppercase the symbol before storing
- **Validate symbol:** Call Schwab quote endpoint to verify the symbol exists. If Schwab returns no data, return 400 with `{error: "Symbol not found: XXXX"}`
- **Ignore duplicates:** If symbol already exists in this watchlist, return 200 with the existing record (don't error)
- Must belong to authenticated user
- Response: `{symbol, added_at}`

### DELETE /api/v1/watchlists/{watchlist_id}/symbols/{symbol}
- Removes symbol from watchlist
- Must belong to authenticated user
- Response: 204 No Content

### GET /api/v1/watchlists/sources
- Returns available scan sources for the Security Strategies page
- Response: `{watchlists: [{id, name, symbol_count}], builtin: [{id: "all-positions", name: "All Positions", symbol_count: N}]}`
- `all-positions` symbol_count comes from `SELECT COUNT(DISTINCT symbol) FROM positions WHERE status = 'ACTIVE'`

### Auth Pattern
- Use the same MSAL auth pattern as `positions_routes.py`
- Extract user_id from the JWT token
- All endpoints require authentication
- All queries filter by user_id (users can only see their own watchlists)

### Router Registration
- Register the router in `app/main.py` with prefix `/api/v1/watchlists` and tag `watchlists`
- Follow the same registration pattern as other routers

---

## Step 3 — Wire Scan Endpoint to Accept Watchlist Source

Find the existing scan endpoint (likely in `scan_routes.py` or `security_strategies_routes.py`) that the Security Strategies "Scan now" button calls.

Modify it to accept a `source` parameter:
- `source=watchlist:{id}` — fetch symbols from `watchlist_symbols` where `watchlist_id = {id}`
- `source=all-positions` — fetch unique symbols from `positions` where `status = 'ACTIVE'`
- Keep backward compatibility with any existing source parameter values

The scan logic itself doesn't change — it already knows how to score a list of symbols. We're just changing where the symbol list comes from.

---

## Acceptance Criteria

1. Both tables exist in Azure SQL with correct schema
2. `GET /api/v1/watchlists` returns empty array initially, then creates default "My Watchlist" on first call
3. Full CRUD cycle works: create watchlist → add symbols → list symbols → remove symbol → delete watchlist
4. Cannot delete default watchlist (returns 400)
5. Symbol validation via Schwab quote — invalid symbols rejected with clear error
6. Duplicate symbol add returns 200 (no error)
7. All endpoints require MSAL auth and filter by user_id
8. Scan endpoint accepts `source=watchlist:{id}` and returns strategy scores for those symbols
9. No existing tests broken

## Commit Message
```
OTA-444, OTA-445: Named watchlists — database schema and backend API

- Create watchlists and watchlist_symbols tables in Azure SQL
- Add watchlist CRUD endpoints (create, rename, delete, list)
- Add symbol management endpoints (add, remove, list per watchlist)
- Lazy default watchlist creation on first access
- Symbol validation via Schwab quote lookup
- Wire scan endpoint to accept watchlist source
- All endpoints require MSAL auth, scoped to user_id
```

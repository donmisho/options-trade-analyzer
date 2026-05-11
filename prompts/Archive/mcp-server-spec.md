# OTA MCP Server — Live Market Data for claude.ai Chats

**Last Updated:** 05-07-2026
**Governing Epic:** OTA-604 (Phase 4 — MCP integration; OTAR Category: OTAR-21)
**Status:** Active build — auth model pivoted to Entra OAuth 2.1 (05-07-2026)
**MCP Server Name:** `ota-market-data`

---

## Table of Contents

- [Goal](#goal)
- [Scope](#scope)
- [Out of Scope](#out-of-scope)
- [ADR-1: Mount on Existing App Service](#adr-1-mount-on-existing-app-service)
- [ADR-2: Microsoft Entra as OAuth 2.1 Authorization Server](#adr-2-microsoft-entra-as-oauth-21-authorization-server)
- [ADR-3: User Binding via Entra OID Claim](#adr-3-user-binding-via-entra-oid-claim)
- [ADR-4: Pass-Through to Existing Provider Adapters](#adr-4-pass-through-to-existing-provider-adapters)
- [Tool Specifications](#tool-specifications)
- [Error Shape](#error-shape)
- [Observability](#observability)
- [Hosting and Deployment](#hosting-and-deployment)
- [Acceptance Criteria](#acceptance-criteria)
- [Story Breakdown](#story-breakdown)
- [Dependencies](#dependencies)
- [Phase 4 Note](#phase-4-note)

---

## Goal

Expose four existing OTA capabilities — live quotes, option chains, simple moving averages, and confirmed earnings dates — to claude.ai conversations through a Model Context Protocol (MCP) server, eliminating the need to paste live market data during trade evaluation and strategy validation chats.

The server's identifier in claude.ai is `ota-market-data`. Tool calls in claude.ai conversations appear as `ota-market-data:get_quote`, `ota-market-data:get_option_chain`, and so on.

## Scope

Exactly four tools. All read-only. All backed by existing OTA capabilities.

| Tool | Backed By |
|---|---|
| `get_quote(ticker)` | `SchwabMarketData.get_quote()` |
| `get_option_chain(ticker, expiration, ...)` | `SchwabMarketData.get_chain()` |
| `get_smas(ticker, periods)` | Existing SMA computation behind the SMA chart UI |
| `get_earnings_date(ticker)` | `FinnhubEarnings` adapter (OTA-508) |

The MCP server is a thin transport layer over what already exists. No new analysis logic, no new data sources, no new caching.

## Out of Scope

Explicitly excluded from this Epic:

- Any AI-call tool (no `evaluate_trade`, no narrative generation)
- Trade scoring or strategy scoring tools
- Historical or derived data not already computed (no IV rank, no ATR)
- Order placement (architecturally out of scope forever, regardless of phase)
- Multi-user authentication (the Entra app reg is single-user by config — Don's OID only)
- New deployment infrastructure
- Frontend changes to OTA

These are deliberate exclusions, not deferrals to a later sprint within this Epic. Adding any of them requires a separate Epic.

---

## ADR-1: Mount on Existing App Service

**Decision Date:** 05-07-2026
**Change Log:** Initial decision

The MCP server is implemented as `app/api/mcp_routes.py` mounted at `/mcp` inside the existing FastAPI process. It deploys through the existing `build-on-push.yml` pipeline. No new Azure resources, no new domain, no new deploy.

- Prod URL: `https://oa.tmtctech.ai/mcp`
- Dev URL: `https://oa-dev.tmtctech.ai/mcp`
- Same App Service plan, same Cloudflare frontend, same managed identity for Key Vault and Azure SQL

This conforms to Pattern 7 (Single Origin via Cloudflare → App Service) in `architecture-plan.md`. Cloudflare Tunnel, Fly.io, and Cloudflare Workers are not used.

## ADR-2: Microsoft Entra as OAuth 2.1 Authorization Server

**Decision Date:** 05-07-2026
**Change Log:** Initial decision (supersedes the 2026-05-07 morning bearer-token decision, which was retired the same day after claude.ai's custom-connector UI was confirmed to require OAuth 2.0 Client ID/Secret rather than static bearer tokens).

Auth on `/mcp/*` follows the OAuth 2.1 Resource Server pattern from the MCP specification. Microsoft Entra acts as the Authorization Server; OTA's `/mcp` endpoint acts as the Resource Server. The claude.ai connector handles the OAuth dance with Entra; OTA never sees the user's Entra password and never holds a refresh token for the MCP path.

- A new Entra app registration named `ota-mcp-server` is created — separate from the BFF app registration (`f11ea8b8-bbce-474b-8d3f-758654245a73`) so it can be revoked, rotated, and scoped independently
- The new app registration uses **client secret** auth (not certificate), because claude.ai's connector UI provides Client ID and Client Secret fields, not certificate upload. Tenant policy permits secrets for this app reg as a documented exception narrowly scoped to the MCP integration.
- The app registration exposes a single API scope: `mcp.invoke` (granted to the `ota-mcp-server` API). All four tools are gated by this single scope.
- The MCP Python SDK's `mcp.server.auth.TokenVerifier` validates each incoming access token: signature against Entra's JWKS, audience matches the `ota-mcp-server` app's Application ID URI, scope contains `mcp.invoke`, and the token is unexpired.
- The server publishes `/.well-known/oauth-protected-resource/mcp` per the MCP spec so claude.ai can discover the Authorization Server and required scope automatically.
- The BFF cookie/CSRF middleware does **not** apply to `/mcp/*` because claude.ai is not a browser session.
- Missing or invalid token returns HTTP 401 with a `WWW-Authenticate: Bearer resource_metadata="<discovery-url>"` header per the MCP spec, allowing claude.ai to initiate the OAuth flow.

This is appropriate for a single-user personal tool. The `ota-mcp-server` app registration's User assignment is restricted to Don's Entra account; if MCP access ever needs to be granted to additional users, that's a User assignment change in the Entra portal, not a code change.

## ADR-3: User Binding via Entra OID Claim

**Decision Date:** 05-07-2026
**Change Log:** Initial decision (supersedes the morning system-principal-from-admin-role decision, which assumed a static system principal under bearer auth).

Every authenticated MCP request resolves to a `User` row by extracting the `oid` claim from the validated JWT and looking up the row where the Entra OID column matches. This mirrors how OTA-455's BFF resolver maps Entra-authenticated browser sessions to `User` rows; the MCP path uses the same mapping logic (extracted into a shared helper if necessary, per OTA-605 Phase 1).

- The `oid` claim is the immutable Entra Object ID for the authenticated user. It is not the email address (which can change) and not the `sub` claim (which is per-app-registration scoped, so it differs between the BFF app and the MCP app for the same physical user).
- The exact `User` table column name holding the OID is to be discovered by OTA-605 Phase 1 by reading `app/models/database.py` and the BFF resolver in `app/auth/dependencies.py` and `app/auth/session_manager.py`. The MCP resolver mirrors whatever the BFF already does — no new schema, no new column.
- All MCP tool calls operate against the resolved user's data scope: `agent_run_log` rows are written under their `user_id`, Schwab tokens used are theirs, and any future per-user logic respects their preferences.
- For the single-user reality today, the resolved user is always Don. For future multi-user expansion, the same code works unchanged once additional User assignments are added in the Entra portal.

## ADR-4: Pass-Through to Existing Provider Adapters

**Decision Date:** 05-07-2026
**Change Log:** Initial decision (unchanged from morning — provider pass-through is auth-model-independent).

MCP tools call existing internal capabilities, never duplicate them. The pattern is:

1. `_get_provider("market_data")` returns the Active Schwab adapter (Pattern 1)
2. The MCP tool function calls the adapter's existing method
3. The MCP tool serializes the result into the documented JSON shape
4. No additional caching is added at the MCP layer — provider-level caching is sufficient

If an existing capability requires refactoring to be callable from `mcp_routes.py` (e.g., the SMA computation lives only inside an HTTP route handler, not a callable service function), the refactor is part of the Story but the analysis logic itself does not change.

---

## Tool Specifications

### `get_quote`

**Purpose:** Live underlying snapshot for picking strikes, computing cushion, and verifying market state.

**Params:**
```json
{ "ticker": "string (required, uppercase)" }
```

**Returns:**
```json
{
  "ticker": "QQQ",
  "price": 625.43,
  "bid": 625.41,
  "ask": 625.45,
  "volume": 28734512,
  "prev_close": 624.18,
  "change_pct": 0.20,
  "timestamp": "2026-05-07T14:32:18Z",
  "market_state": "REGULAR"
}
```

`market_state`: one of `PRE`, `REGULAR`, `POST`, `CLOSED`.

**Source:** `SchwabMarketData.get_quote()`.

### `get_option_chain`

**Purpose:** Strikes with bid, ask, IV, greeks, volume, and open interest for a given expiration. The headline tool — eliminates the paste-bid/ask workflow.

**Params:**
```json
{
  "ticker": "string (required)",
  "expiration": "string YYYY-MM-DD (required)",
  "option_type": "string optional, one of 'call'|'put'|'both', default 'both'",
  "strike_range_pct": "number optional, default 0.15"
}
```

**Returns:**
```json
{
  "ticker": "QQQ",
  "underlying_price": 625.43,
  "expiration": "2026-06-19",
  "dte": 43,
  "options": [
    {
      "occ_symbol": "QQQ_061926C630",
      "strike": 630.00,
      "type": "call",
      "bid": 4.15,
      "ask": 4.25,
      "mid": 4.20,
      "last": 4.18,
      "volume": 12453,
      "open_interest": 84321,
      "iv": 0.247,
      "delta": 0.38,
      "gamma": 0.012,
      "theta": -0.18,
      "vega": 0.42
    }
  ]
}
```

`strike_range_pct` filters strikes to within ±15% of underlying by default. Without this, returning a full chain on QQQ is hundreds of strikes. Override only when explicitly needed.

**Source:** `SchwabMarketData.get_chain()`. The OCC symbol format must match Schwab's actual return shape — Phase 1 of OTA-606 verifies this against a live response before serialization is locked in.

### `get_smas`

**Purpose:** Simple moving averages for trend alignment checks during evaluation.

**Params:**
```json
{
  "ticker": "string (required)",
  "periods": "array of integers, optional, default [8, 21, 50]"
}
```

**Returns:**
```json
{
  "ticker": "QQQ",
  "current_price": 625.43,
  "smas": {
    "8":  { "value": 622.18, "price_vs_sma_pct": 0.52 },
    "21": { "value": 618.45, "price_vs_sma_pct": 1.13 },
    "50": { "value": 615.76, "price_vs_sma_pct": 1.57 }
  },
  "alignment": "bullish",
  "as_of": "2026-05-07"
}
```

`alignment`: `bullish` (price above all requested SMAs), `bearish` (price below all), `mixed`, `neutral`.
`price_vs_sma_pct`: positive when price is above the SMA, negative when below. Used directly for the "extended >5% below 50-day" framework flag.

Default periods reflect the framework's standard set. Callers can request other periods. The Story does not include a 200-day default — add separately if needed.

**Source:** Existing SMA computation behind the SMA chart UI. OTA-607 already shipped this tool against the morning's bearer-auth foundation; OTA-605's Entra rework re-validates the tool still functions under the new auth path as part of its acceptance matrix.

### `get_earnings_date`

**Purpose:** Confirmed next earnings date for the no-earnings-holds framework rule.

**Params:**
```json
{ "ticker": "string (required)" }
```

**Returns (equity):**
```json
{
  "ticker": "MSFT",
  "next_earnings": {
    "date": "2026-07-29",
    "time": "after_close",
    "confirmed": true,
    "source": "finnhub"
  },
  "days_until": 83
}
```

**Returns (ETF — QQQ, SPY, IWM, etc.):**
```json
{
  "ticker": "QQQ",
  "next_earnings": null,
  "is_etf": true
}
```

ETFs auto-satisfy the no-earnings-holds rule. The `is_etf` flag is informational — `next_earnings: null` is the contract.

**Source:** `FinnhubEarnings` adapter (the same provider that powers the `EarningsInWindowGate` hard gate).

---

## Error Shape

Errors return as structured response bodies, not stack traces. HTTP status remains 200 for tool-level errors so claude.ai can read the error and respond intelligently. Only auth and transport failures return non-200.

```json
{
  "error": {
    "code": "TICKER_NOT_FOUND",
    "message": "No data found for ticker XYZ",
    "ticker": "XYZ"
  }
}
```

Codes used:

| Code | When |
|---|---|
| `TICKER_NOT_FOUND` | Symbol not in Schwab's universe or `symbol_reference` |
| `EXPIRATION_INVALID` | Date format wrong or expiration not available for ticker |
| `SCHWAB_UNAVAILABLE` | Upstream Schwab API down or rate limited |
| `EARNINGS_DATA_UNAVAILABLE` | Finnhub has no record for this ticker |
| `INSUFFICIENT_HISTORY` | Not enough price history for requested SMA period |

Auth failures return non-200 status:

| HTTP Status | When |
|---|---|
| `401 Unauthorized` (with `WWW-Authenticate` header) | Missing, invalid, or expired Entra access token |
| `403 Forbidden` | Token validates but `mcp.invoke` scope absent, or `oid` claim does not resolve to a `User` row |

---

## Observability

Every MCP tool call writes one row to `agent_run_log` per Pattern 3 (Two-Track Observability). The row records:

- `tool_name` (e.g., `mcp.get_quote`)
- `ticker`
- `user_id` (resolved from JWT `oid` claim per ADR-3)
- `latency_ms`
- `success` boolean and `error_code` on failure
- OTel `trace_id` from the wrapping span

Failed observability writes never block the primary tool response. Fire-and-forget per the architecture plan.

---

## Hosting and Deployment

| Concern | Decision |
|---|---|
| MCP server name | `ota-market-data` |
| Module location | `app/api/mcp_routes.py` |
| Mount path | `/mcp` (registered in `app/main.py` alongside other routers) |
| OAuth discovery | `/.well-known/oauth-protected-resource/mcp` (RFC 9728) |
| Transport | Streamable HTTP per the MCP spec |
| Pipeline | Existing `build-on-push.yml` |
| Prod URL | `https://oa.tmtctech.ai/mcp` |
| Dev URL | `https://oa-dev.tmtctech.ai/mcp` |
| Authorization Server | Microsoft Entra (tenant `tmtctech-team.atlassian.net` Entra tenant) |
| App registration | `ota-mcp-server` — separate from BFF (`f11ea8b8-bbce-474b-8d3f-758654245a73`) |
| Credential type | Client secret (in `options-analyzer` Key Vault as `mcp-entra-client-secret`) |
| Required scope | `api://<ota-mcp-server-app-id>/mcp.invoke` |
| Token validation | `mcp.server.auth.TokenVerifier` against Entra JWKS (`https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys`) |
| Audience | `api://<ota-mcp-server-app-id>` |
| User assignment | Restricted to Don's Entra account (single-user) |
| claude.ai connector | Settings → Connectors → Add custom connector → URL above, OAuth Client ID + Secret pasted into Advanced Settings |

claude.ai will not accept a self-signed local cert, so end-to-end connector testing happens against the dev URL, not against `https://127.0.0.1:8000`. Local-machine testing with the MCP Inspector is permitted before the dev push (the Inspector can be run against a local dev URL with a manually obtained access token, bypassing the OAuth UI).

**Entra app registration redirect URIs** (configured in the Entra portal during Don's setup work):
- `https://claude.ai/api/mcp/auth_callback`
- `https://claude.com/api/mcp/auth_callback`

Both are required because claude.ai may use either domain depending on the user's session.

---

## Acceptance Criteria

### Build and tool-level acceptance

- All four tools return correct data for QQQ, SPY, MSFT, AAPL, and at least one mid-cap (e.g., RL or VRT)
- ETF tickers return `next_earnings: null, is_etf: true` from `get_earnings_date`
- Errors return structured codes from the table above, never stack traces
- Each call writes a row to `agent_run_log` with the correct `tool_name`, resolved `user_id`, and `latency_ms`

### Auth and discovery acceptance

- Missing or invalid token returns 401 with `WWW-Authenticate` header pointing at the discovery URL
- Token with valid signature but missing `mcp.invoke` scope returns 403
- Token with valid signature and scope but `oid` claim that doesn't map to a `User` row returns 403
- `GET /.well-known/oauth-protected-resource/mcp` returns valid RFC 9728 discovery JSON
- JWKS validation correctly rejects tokens signed with the wrong key

### claude.ai connector acceptance

- claude.ai connector configured against the dev URL with the Client ID + Client Secret pasted into Advanced Settings shows the `ota-market-data` server with all four tools in the available tool list
- The OAuth dance from claude.ai → Entra → claude.ai → OTA completes without manual intervention beyond the initial Entra consent screen
- claude.ai can invoke each tool inline during a conversation and receive correctly shaped JSON
- Production deploy follows the standard `build-on-push.yml` flow with no new pipeline steps

---

## Story Breakdown

The Epic (OTA-604) consists of five Stories. The morning's bearer-auth attempt landed two of them on `origin/main` (OTA-605 foundation and OTA-607 SMA tool). The afternoon Entra pivot reshapes the work as follows:

1. **OTA-605 — Auth pivot to Entra Resource Server.** Modify the existing `mcp_routes.py` to remove the bearer-token middleware and admin-role system-principal resolver, and replace with Entra Resource Server pattern using `mcp.server.auth.TokenVerifier`. Add `/.well-known/oauth-protected-resource/mcp` discovery endpoint. Implement OID-claim-to-`users`-table resolution mirroring the BFF resolver. Verify OTA-607's `get_smas` tool still works under the new auth foundation (acceptance gate).

2. **OTA-606 — `get_quote` and `get_option_chain`.** The two snapshot tools that share the Schwab adapter path. Highest user value. Builds on OTA-605's Entra-validated foundation.

3. **OTA-607 — `get_smas`.** Already shipped on `origin/main` (commit `c086c39`) prior to the auth pivot. No new build work. Re-validated as part of OTA-605's acceptance.

4. **OTA-608 — `get_earnings_date`.** Wraps `FinnhubEarnings`. Includes ETF detection via `symbol_reference` table.

5. **OTA-609 — Connector configuration and acceptance.** Configure claude.ai Settings → Connectors against dev with the Entra Client ID + Secret, run the full acceptance matrix against dev and prod, document the Entra credential rotation procedure as an ADR section in `auth-process.md`.

OTA-606, OTA-608 can run in parallel after OTA-605 is merged. OTA-609 waits on all four upstream Stories.

---

## Dependencies

- **Schwab market data live and current.** Already true.
- **`FinnhubEarnings` adapter live.** Already true (OTA-508).
- **Existing SMA computation reachable from Python (not exclusively via HTTP).** Already true — OTA-607 shipped against the SMA service function path on 05-07-2026 morning.
- **MCP Python SDK (`pip install mcp`) with auth submodule.** Already in `requirements.txt` from the morning's OTA-605 commit; OTA-605's Entra rework imports `mcp.server.auth.TokenVerifier` from the same package version.
- **Entra app registration `ota-mcp-server`.** Don creates this manually in the Entra portal before OTA-605 verification. See the separate Entra portal action items doc.
- **Entra client secret in `options-analyzer` Key Vault** as `mcp-entra-client-secret`. Don adds this manually after generating the secret in the Entra portal.
- **claude.ai connector configuration.** Requires Don to configure the connector via Settings → Connectors after OTA-609; not a build dependency.

---

## Phase 4 Note

This Epic is the entirety of Phase 4 (MCP integration) per the `architecture-plan.md` phase history table. After this ships, Phase 4 status changes from "Not started" to "Active" or "Complete." Future MCP additions (e.g., trade scoring, AI evaluation, backtest data) are separate Epics with their own OTAR linkage and their own ADRs.

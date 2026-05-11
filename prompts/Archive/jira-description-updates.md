# Jira Description Updates — OTA-604 (Epic) and OTA-605 (Story)

These reflect the 05-07-2026 afternoon pivot from static bearer token to Microsoft Entra OAuth 2.1 Resource Server pattern.

Two delivery options:
1. Push via Atlassian MCP from Claude Web (just say "push these to Jira")
2. Paste the markdown below into each ticket's description field manually

---

## OTA-604 (Epic) — new description

```markdown
# OTA Market Data MCP Server

Expose four existing OTA capabilities — live quotes, option chains, simple moving averages, and confirmed earnings dates — to claude.ai conversations through a Model Context Protocol (MCP) server. Eliminates the need to paste live market data during trade evaluation and strategy validation chats.

## Auth model

Microsoft Entra OAuth 2.1 with the `ota-mcp-server` app registration as the Authorization Server and OTA's `/mcp` endpoint as the Resource Server (per MCP spec and RFC 9728). The MCP Python SDK's `mcp.server.auth.TokenVerifier` validates each access token against Entra's JWKS, audience (`api://<ota-mcp-server-app-id>`), and the `mcp.invoke` scope. Don pastes the Client ID + Client Secret into claude.ai's connector Advanced Settings; the OAuth dance happens entirely between claude.ai and Entra.

A 2026-05-07 morning attempt with static bearer tokens was retired the same day after claude.ai's custom-connector UI was confirmed to require OAuth Client ID/Secret rather than static tokens.

## Scope (4 tools, all read-only)

- `get_quote(ticker)` — live underlying snapshot
- `get_option_chain(ticker, expiration, ...)` — strikes with bid/ask/IV/greeks/volume/OI
- `get_smas(ticker, periods)` — simple moving averages (default 8/21/50)
- `get_earnings_date(ticker)` — confirmed next earnings; ETFs return `is_etf: true`

## Out of scope

- Any AI-call tool (no evaluate_trade)
- Trade scoring or strategy scoring tools
- Order placement (architecturally out of scope forever)
- Multi-user auth (single-user via Entra User assignment restriction)

## Stories

- OTA-605: Auth pivot to Entra Resource Server (modifies existing `mcp_routes.py`)
- OTA-606: Add `get_quote` and `get_option_chain` tools
- OTA-607: `get_smas` — already shipped on `origin/main` as `c086c39` morning of 2026-05-07; re-validated by OTA-605 acceptance
- OTA-608: Add `get_earnings_date` with ETF detection via `symbol_reference`
- OTA-609: Configure claude.ai OAuth connector and run E2E acceptance (dev + prod)

## Source of truth

- Spec: `claude_context/mcp-server-spec.md`
- Entra portal setup: `claude_context/entra-portal-action-items.md`
- Phase 4 in `architecture-plan.md` Phase History table — flips to Active/Complete after OTA-609 ships

## OTAR linkage

OTAR-21 (MCP Integration category)
```

---

## OTA-605 (Story) — new description

```markdown
# Pivot MCP auth from bearer token to Entra OAuth 2.1 Resource Server

## What changed and why

The morning of 2026-05-07 shipped OTA-605 (foundation) and OTA-607 (`get_smas`) to `origin/main` against a static-bearer-token auth model. That model was retired the same afternoon after claude.ai's custom-connector UI was confirmed to require OAuth 2.0 Client ID + Client Secret, not static bearer tokens. This Story replaces the bearer auth layer in the existing `app/api/mcp_routes.py` with the Microsoft Entra OAuth 2.1 Resource Server pattern from the MCP spec.

The 605/607 commits stay on `main`. The auth swap happens on a fresh feature branch (`feat/OTA-605-entra-resource-server`) that modifies the existing file rather than building from scratch. OTA-607's `get_smas` tool keeps working through the swap because the tool is auth-model-independent.

## What this Story does

1. Removes the bearer-token middleware (`verify_mcp_bearer`) and the admin-role system principal resolver from `mcp_routes.py`
2. Wires `mcp.server.auth.TokenVerifier` into the FastMCP instance, validating against Entra's JWKS, the `ota-mcp-server` app registration's audience, and the `mcp.invoke` scope
3. Implements OID-claim-to-`users`-table resolution mirroring the BFF resolver in `app/auth/dependencies.py` and `app/auth/session_manager.py`
4. Adds `/.well-known/oauth-protected-resource/mcp` discovery endpoint per RFC 9728
5. Updates `mcp_tool_observability` to use the per-request resolved `user_id`
6. Re-validates OTA-607's `get_smas` tool works under the new auth foundation
7. Adds a brief MCP Resource Server section to `auth-process.md` (rotation procedure handled separately by OTA-609)

## Prerequisites Don must complete before kickoff

Tracked in `claude_context/entra-portal-action-items.md`:

- New `ota-mcp-server` Entra app registration created (separate from BFF app reg)
- Client secret generated and stored in `options-analyzer` Key Vault as `mcp-entra-client-secret`
- `mcp.invoke` scope defined; Application ID URI captured
- User assignment restricted to Don's account
- Redirect URIs added: `https://claude.ai/api/mcp/auth_callback` and `https://claude.com/api/mcp/auth_callback`
- Unstaged 606/608 working changes discarded
- Fresh feature branch created off `main`

## Open question Phase 1 must answer

How does the BFF map Entra OID to `users` table rows today? The exact column name on the `User` model holding the OID is to be discovered in Phase 1 by reading `app/models/database.py`, `app/auth/dependencies.py`, and `app/auth/session_manager.py`. The MCP resolver mirrors whatever the BFF already does.

## Acceptance gate

- 401 with `WWW-Authenticate` header on missing/invalid token
- 403 on valid signature but missing scope or unprovisioned OID
- `/.well-known/oauth-protected-resource/mcp` returns valid RFC 9728 JSON
- OTA-607's `get_smas("QQQ")` tool returns documented shape under the new auth foundation, called via MCP Inspector with a real Entra access token
- `agent_run_log` records the call with the resolved `user_id` (Don's, mapped from his Entra OID)
- Brief MCP Resource Server ADR section added to `auth-process.md`

## Build prompt

Located at `prompts/OTA-605.md` (rewritten 05-07-2026 afternoon).

## Coordination

Blocks OTA-606 and OTA-608. OTA-607 stays on `main` unchanged.
```

---

## Atlassian MCP push instructions (if Don wants me to do it)

If you want me to push these via the Atlassian MCP, I'll use the `Atlassian:editJiraIssue` tool with:
- `cloudId`: `53c395d7-bac7-4a5f-baf2-ee2b0f375a2b`
- `issueIdOrKey`: `OTA-604` then `OTA-605`
- `contentFormat`: `markdown`
- `fields`: `{ "description": "<the markdown above>" }`

Just say "push the Jira updates" and I'll fire both calls.

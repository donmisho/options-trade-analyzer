```yaml
---
allowedTools:
  - Read
  - Grep
  - Glob
  - Bash(cat*)
  - Bash(git*)
  - Bash(python*)
  - Bash(az*)
  - Bash(Invoke-WebRequest*)
  - Bash(Invoke-RestMethod*)
---
```

# OTA-855 — Add the `ota-market-data` connector to claude.ai for the Short-DTE Trade Lab dashboard

The dashboard reads two new MCP tools, `get_trade_fills` and `get_schwab_status`, through the analyzer's MCP server. claude.ai connectors are added in the claude.ai web UI, which Claude Code cannot drive, so this prompt has two halves: Claude Code verifies every prerequisite and gathers the exact values; Don pastes them into claude.ai. Do NOT run `git commit` or `git push`, do NOT create or rotate any Entra secret, and do NOT edit any file under `claude_context/`. Never print a secret value into the chat; copy it to the clipboard instead.

## Mechanism A — Required Reading (run first)

```powershell
Set-Location "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
cat claude_context/CLAUDE.md
cat claude_context/auth-process.md
cat prompts/Archive/entra-portal-action-items.md
cat prompts/Archive/OTA-609.md
cat docs/runbooks/account-activity-poller.md
```

## Mechanism B — Governing rules embedded

* The MCP server is an OAuth 2.1 Resource Server (auth-process.md ADR-3). Microsoft Entra is the Authorization Server; the `ota-mcp-server` app registration exposes the `mcp.invoke` scope; claude.ai is the OAuth client and holds the app registration's Client ID and Client Secret in the connector's Advanced Settings.
* The client secret lives in the `options-analyzer` Key Vault as `mcp-entra-client-secret`. The resource server never uses it; only the connector does.
* The connector's server URL is `https://oa.tmtctech.ai/mcp/` with the trailing slash (main.py mounts the sub-app at `/mcp` and Starlette strips the prefix). The name shown to claude.ai is `ota-market-data`.
* A token is accepted only when its `oid` claim matches a row in `users`. Don's row must exist and be active.
* The two new tools exist on the server only once the `OTA-855-account-activity-poller` branch is deployed to the environment the connector points at. Until then the connector lists the four original tools (`get_quote`, `get_option_chain`, `get_smas`, `get_earnings_date`).
* Don holds every deploy and Jira gate. Claude Code reports; it does not advance tickets.

## Step 1 — Which environment

Ask Don whether the connector should point at prod (`https://oa.tmtctech.ai/mcp/`) or dev (`https://oa-dev.tmtctech.ai/mcp/`). Prod is the dashboard's target; dev is right only while OTA-855 is deployed to dev alone. Use the chosen base URL below as `<base>`.

## Step 2 — Is the server up, and which tools does it have

```powershell
Invoke-RestMethod -Uri "<base-without-/mcp/>/.well-known/oauth-protected-resource/mcp"
Invoke-RestMethod -Uri "<base-without-/mcp/>/health"
```

Expected: the discovery JSON names `https://login.microsoftonline.com/<tenant>/v2.0` as the authorization server and `api://<client-id>/mcp.invoke` under `scopes_supported`; `/health` says healthy. Record the `resource` value: it is the Application ID URI, and the client id is the part after `api://`.

Then check whether OTA-855 is deployed there:

```powershell
git fetch origin
git log --oneline origin/main -5
```

If `origin/main` does not contain the OTA-855 commits (`41d873c`, `fc880e5`), the server still has only the four original tools. Say so in the report; the connector can still be added now and picks the new tools up after the deploy (Step 6).

## Step 3 — Entra app registration checks

Sign in to Azure if needed (`az login`), then:

```powershell
az ad app list --display-name ota-mcp-server --query "[].{appId:appId, uri:identifierUris, redirects:web.redirectUris, scopes:api.oauth2PermissionScopes[].value}" -o json
```

Confirm:

* `appId` equals the client id from Step 2.
* `identifierUris` holds `api://<appId>`.
* `redirectUris` holds both `https://claude.ai/api/mcp/auth_callback` and `https://claude.com/api/mcp/auth_callback`.
* `scopes` holds `mcp.invoke`.

If a redirect URI or the scope is missing, stop and report; adding it is Don's portal action (entra-portal-action-items.md steps 2 and 4), not Claude Code's.

## Step 4 — The secret, to the clipboard only

```powershell
az keyvault secret show --vault-name options-analyzer --name mcp-entra-client-secret --query value -o tsv | Set-Clipboard
```

Say "client secret copied to the clipboard" and nothing else about it. If the secret is missing or expired in the app registration (`az ad app credential list --id <appId>` shows no current `endDateTime`), stop and report: a new secret is Don's portal action, followed by the Key Vault update in the ADR rotation procedure.

## Step 5 — Don's users row

With the venv active and `.env` pointing at the same database the chosen environment uses, run a short Python snippet against `app.models.session.async_session` that selects `id, email, role, is_active` from `users` for Don's email. Confirm one active row whose `id` is Don's Entra OID (the `oid` claim, a GUID). If there is none, stop and report; the token verifier rejects an unprovisioned OID with 401.

## Step 6 — Hand Don the click path

Print this, with the real values filled in:

1. claude.ai → Settings → Connectors → Add custom connector.
2. Name: `ota-market-data`. Remote MCP server URL: `<base>` (with the trailing slash).
3. Advanced settings → OAuth Client ID: `<appId>`. OAuth Client Secret: paste from the clipboard.
4. Add, then Connect. Sign in with the Entra account and consent to `Invoke OTA MCP tools` once.
5. Open the connector's tool list. Expected now: `get_quote`, `get_option_chain`, `get_smas`, `get_earnings_date`, and, once OTA-855 is deployed to that environment, `get_trade_fills` and `get_schwab_status`. If the two new tools do not appear after the deploy, disconnect and reconnect the connector so claude.ai refreshes the tool list.
6. In a new claude.ai chat, enable the connector and ask: "Call get_schwab_status on ota-market-data." Expected: JSON with `connected`, `app_url` `https://oa.tmtctech.ai/` (or the dev address) and `last_sync`.

Ask Don to report the exact connector name as it appears in claude.ai and whether both new tools are listed.

## Step 7 — Report

End with: the environment chosen, the discovery endpoint's `resource` value, whether OTA-855 is deployed there, the three Entra checks (pass or what is missing), whether the secret was found, whether Don's users row exists, and the connector name Don reported. The connector name is what the Short-DTE Trade Lab dashboard's `fills_db` and `schwab_status` datasets need next; Don passes it to the dashboard chat.

Post-build QA level: 0 (no code change) — verification only.

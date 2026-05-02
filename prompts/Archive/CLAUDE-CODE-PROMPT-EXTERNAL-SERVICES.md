# OTA-500 External Services Connection Screen — Claude Code Prompt

## Jira
- Ticket: OTA-500
- Epic: OTA-455 (Identity Management Foundation)
- Commit prefix: `OTA-500`

## Preparation

```bash
cat CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/SCHWAB-LOGIN-PROCESS.md
cat claude_context/auth-process.md
cat claude_context/UI-GUIDANCE.md
cat web/src/components/StartupProgress.jsx
cat web/src/context/AuthContext.jsx
cat web/src/api/client.js
cat app/api/schwab_auth_routes.py
cat app/providers/schwab_token_manager.py
ls app/api/
ls web/src/components/
```

Read all files above before making any changes. Understand the current startup flow and Schwab OAuth popup pattern.

## Problem

The current startup flow has a "Checking Schwab connection" step that automatically checks Schwab status with a timeout. Whether it succeeds or times out, the user has no control — they just watch it happen. The correct design is an **interactive External Services screen** that replaces this automatic check, showing the user which external services are available and letting them choose to connect before the app finishes loading.

This aligns with `architecture-plan.md` Pattern 1 (Provider Adapter Pattern) — every external data source implements a standard interface with its own credential lifecycle, and the UI should present a registry of available services.

## What to Build

### 1. Backend: New endpoint `GET /api/v1/services/status`

Create a new route file `app/api/service_routes.py` (or add to an existing appropriate routes file).

This endpoint returns a list of registered external services and their connection status:

```json
{
  "services": [
    {
      "id": "schwab",
      "name": "Charles Schwab",
      "description": "Market Data & Trading",
      "active": true,
      "connected": false,
      "auth_type": "oauth",
      "login_url": "/api/v1/auth/schwab/login"
    },
    {
      "id": "tradier",
      "name": "Tradier",
      "description": "Market Data (Deprecated)",
      "active": false,
      "connected": false,
      "auth_type": "api_key",
      "login_url": null
    }
  ]
}
```

Implementation:
- For Schwab: call `SchwabTokenManager` to check if tokens exist and are valid (same logic as existing `/auth/schwab/status`).
- For Tradier: always return `active: false, connected: false`.
- The service list should be easy to extend — a simple list/dict of service definitions, not scattered conditionals.
- Register the router in `app/main.py`.
- **Auth requirement**: This endpoint should require a valid session (the user is already authenticated at this point in startup).

### 2. Frontend: Modify StartupProgress to add External Services step

**Replace whatever the current startup step 5 is** (currently some form of "Checking Schwab connection") with a new step: **"Connect External Services"**.

New startup step sequence:
1. Initializing app (0.2s) — unchanged
2. Authenticating with Microsoft — unchanged
3. Connecting to backend — unchanged
4. Verifying user session — unchanged
5. **Connect External Services** — NEW interactive step (replaces "Checking Schwab connection")
6. Ready — unchanged

**When step 5 activates:**

The StartupProgress widget should expand to show an **External Services panel** below the step list. This panel:

- Calls `GET /api/v1/services/status` to get the list of services
- Renders a card for each service showing:
  - Service name and description
  - Status badge: **Connected** (green pill) / **Disconnected** (amber pill) / **Inactive** (gray pill, dimmed text)
  - For active + disconnected services: a "Connect" button
  - For inactive services: grayed out, no button, "Inactive" badge
- Has a **"Continue"** button at the bottom that proceeds to step 6 (Ready)
  - The Continue button is always enabled — user can skip connecting if they want
  - If Schwab is connected, the button text says "Continue"
  - If Schwab is NOT connected, the button text says "Continue without Schwab" (so they know what they're skipping)

**Schwab Connect button behavior:**

When the user clicks "Connect" on the Schwab card:
- Open a popup window to the Schwab login URL (same pattern as the existing Header.jsx Schwab click handler — see `SCHWAB-LOGIN-PROCESS.md`)
- The popup URL comes from the `login_url` field in the service status response
- Poll `GET /api/v1/auth/schwab/status` every 2 seconds while popup is open
- When `connected: true` is returned, close the popup and update the Schwab card to show "Connected" (green)
- Safety timeout: stop polling after 5 minutes
- The "Connect" button should show a spinner/pulsing indicator while the popup is open

**After the user clicks Continue:**
- Mark step 5 as complete (green check)
- If Schwab connected: show elapsed time as usual
- If Schwab skipped: show elapsed time, step still gets green check (it's the user's choice)
- Proceed to step 6 (Ready) — mark it complete and transition to the main app

### 3. Remove the automatic Schwab check step

Whatever the current implementation of the "Checking Schwab connection" step is (including any timeout logic, fallback behavior, or automatic status polling), **remove it entirely**. The Schwab connection is now user-initiated from the External Services panel in step 5. Do not keep any automatic Schwab checking in the startup flow.

### 4. Header Schwab indicator still works

The existing Header.jsx Schwab status indicator should continue to work as before. If the user skipped Schwab during startup, the header shows "Disconnected" and they can click it to connect later (existing behavior). Do NOT remove the header indicator.

## Design Rules

- Dark theme CSS variables only — never inline hex values. Use `var(--bg1)`, `var(--bg2)`, `var(--text1)`, `var(--accent)`, etc.
- `var(--bg2)` restricted to filter bars, QuoteBar, pill badge backgrounds only — never table rows, headers, or panel backgrounds.
- Buttons sized to content with fixed padding, never full-width. Buttons must have visible borders/backgrounds in default state.
- No `$` prefix on monetary values.
- Service cards should use the same visual language as the existing StartupProgress steps — clean, minimal, no heavy borders.
- The services panel should feel like a natural extension of the StartupProgress widget, not a separate modal or page.

## Files to Create/Modify

**Create:**
- `app/api/service_routes.py` — new backend route for `/api/v1/services/status`

**Modify:**
- `app/main.py` — register the new service router
- `web/src/components/StartupProgress.jsx` — replace auto-Schwab-check with interactive services step
- `web/src/api/client.js` — add `getServicesStatus()` function

**Do NOT modify:**
- `web/src/components/Header.jsx` — Schwab indicator stays as-is
- `app/api/schwab_auth_routes.py` — existing Schwab OAuth routes stay as-is
- `app/auth/` — identity auth is a separate concern

## Acceptance Criteria

1. `GET /api/v1/services/status` returns a JSON list of services with `id`, `name`, `description`, `active`, `connected`, `auth_type`, `login_url` fields
2. Schwab shows `connected: true/false` based on actual token state
3. Tradier shows `active: false` and is grayed out in the UI
4. StartupProgress step 5 shows "Connect External Services" instead of "Checking Schwab connection"
5. When step 5 is reached, the services panel appears with Schwab and Tradier cards
6. Clicking Schwab "Connect" opens the OAuth popup (same popup behavior as Header.jsx)
7. After successful Schwab OAuth, the card updates to "Connected" without page reload
8. "Continue" button progresses to Ready step regardless of connection state
9. If user skips Schwab, Header.jsx still shows "Disconnected" and clicking it still works
10. No regressions — the rest of the startup flow (steps 1-4 and step 6) works exactly as before

## Commit

```
OTA-500: Add External Services connection screen to startup flow

- New GET /api/v1/services/status endpoint with provider registry
- Replace auto-Schwab-check with interactive services panel in StartupProgress
- Schwab OAuth popup from services screen (same popup pattern as Header)
- Tradier shown as inactive/deprecated service
- Continue button allows skipping service connection
- Header Schwab indicator unchanged — still works for post-startup connection
```

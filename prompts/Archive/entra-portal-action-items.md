# Entra Portal Action Items — `ota-mcp-server` App Registration

**Owner:** Don (manual setup; not automatable)
**Blocks:** OTA-605 verification
**Related:** mcp-server-spec.md ADR-2

This checklist creates and configures the Entra app registration that backs the `ota-market-data` MCP server. It is separate from the BFF app registration (`f11ea8b8-bbce-474b-8d3f-758654245a73`) so it can be revoked, rotated, and scoped independently.

Complete every step in order before kicking off OTA-605.

---

## 1. Create the app registration

In the Azure portal → Microsoft Entra ID → App registrations → New registration:

- **Name:** `ota-mcp-server`
- **Supported account types:** Accounts in this organizational directory only (single-tenant)
- **Redirect URI:** Leave blank for now — added in step 2

Click Register. Capture from the Overview page:

- **Application (client) ID** — paste into env/App Service config as `ENTRA_MCP_CLIENT_ID`
- **Directory (tenant) ID** — already in use as `ENTRA_TENANT_ID`; confirm it matches

---

## 2. Configure redirect URIs

Open the new app registration → Authentication → Add a platform → Web. Add both redirect URIs:

- `https://claude.ai/api/mcp/auth_callback`
- `https://claude.com/api/mcp/auth_callback`

Both are required because claude.ai may use either domain depending on the user's session. Save.

Under the same Authentication blade:

- **Front-channel logout URL:** leave blank
- **Implicit grant and hybrid flows:** leave both unchecked (Authorization Code Grant only)
- **Allow public client flows:** leave No
- **Supported account types:** confirm "Accounts in this organizational directory only" (no change from registration)

---

## 3. Generate a client secret

Open the app registration → Certificates & secrets → Client secrets → New client secret.

- **Description:** `claude.ai MCP connector`
- **Expires:** 24 months (per tenant policy default)

Click Add. **Immediately copy the secret value** — Entra masks it once you leave the page. There is no recovery — if you miss it you have to delete the secret and create a new one.

Save the value in two places:

1. **`options-analyzer` Key Vault as `mcp-entra-client-secret`:**
   ```powershell
   az keyvault secret set --vault-name options-analyzer --name mcp-entra-client-secret --value "<paste-secret-here>"
   ```
2. **Don's password manager** — needed again later when configuring the claude.ai connector in OTA-609 (Key Vault masks it the same way Entra does after creation).

---

## 4. Expose an API and define the `mcp.invoke` scope

Open the app registration → Expose an API → Set (next to "Application ID URI"):

- **Application ID URI:** Accept the default `api://<client-id>` (Azure prefills it). Capture this value as `ENTRA_MCP_APPLICATION_ID_URI`.

Then → Add a scope:

- **Scope name:** `mcp.invoke`
- **Who can consent:** Admins and users
- **Admin consent display name:** `Invoke OTA MCP tools`
- **Admin consent description:** `Allows the application to invoke MCP tools on the OTA market data server.`
- **User consent display name:** `Invoke OTA MCP tools`
- **User consent description:** `Allows claude.ai to call OTA MCP tools (live quotes, option chains, SMAs, earnings dates) on your behalf.`
- **State:** Enabled

Save.

---

## 5. Restrict User assignment to Don only

Open the app registration → Overview → Managed application in local directory → click the link (takes you to the Enterprise Application blade for this app reg) → Properties:

- **Assignment required?** Yes
- **Visible to users?** No
- Save

Then → Users and groups → Add user/group:

- Select Don's Entra user account
- No role to select (the app has no app roles defined yet)
- Assign

This means only Don's account can authenticate against this app registration. Anyone else who tries to use the connector with the Client ID + Secret will fail at the Entra consent step.

---

## 6. Verify the API permission for the tenant

Open the app registration → API permissions:

- **Configured permissions:** the only entry should be `User.Read` (Delegated, granted automatically on creation). This is fine — the MCP server doesn't need Graph access; the user's identity comes from the JWT claims.
- No additional permissions needed.

---

## 7. Capture configuration values for OTA

After steps 1–6, you should have:

| Value | Where to put it |
|---|---|
| Application (client) ID | `ENTRA_MCP_CLIENT_ID` env var (local) and App Service config (dev + prod) |
| Application ID URI (e.g., `api://<client-id>`) | `ENTRA_MCP_APPLICATION_ID_URI` env var and App Service config |
| Required scope name (`mcp.invoke`) | `ENTRA_MCP_REQUIRED_SCOPE` env var (default already in code) |
| Client secret value | `mcp-entra-client-secret` in Key Vault + password manager |
| Tenant ID | Already in use as `ENTRA_TENANT_ID`; no change |

---

## 8. Smoke-test the OAuth flow before OTA-605 verification

Before kicking off the OTA-605 build prompt, prove the Entra app registration is wired correctly:

```powershell
az login
az account get-access-token --resource api://<ENTRA_MCP_CLIENT_ID>
# Expect a JWT in the output. Decode it at jwt.ms (paste the accessToken value)
# and verify:
#   - aud claim matches api://<ENTRA_MCP_CLIENT_ID>
#   - oid claim is your Entra OID
#   - scp claim contains "mcp.invoke"
#   - iss claim is https://login.microsoftonline.com/<tenant>/v2.0
```

If any of those claims are wrong, fix the app registration before OTA-605 starts. The OTA-605 verification depends on these claims being correct.

---

## 9. Final pre-OTA-605 checklist

- [ ] App registration created
- [ ] Redirect URIs added (both `claude.ai` and `claude.com`)
- [ ] Client secret generated and copied to Key Vault + password manager
- [ ] Application ID URI set
- [ ] `mcp.invoke` scope defined and enabled
- [ ] User assignment restricted to Don only
- [ ] OTA env/App Service config updated with `ENTRA_MCP_CLIENT_ID` and `ENTRA_MCP_APPLICATION_ID_URI`
- [ ] OAuth smoke test passes (token has correct aud, oid, scp, iss claims)
- [ ] Unstaged 606/608 working changes discarded (`git checkout -- app/api/mcp_routes.py app/main.py`)
- [ ] Fresh feature branch created (`git checkout -b feat/OTA-605-entra-resource-server`)

When all boxes are checked, kick off OTA-605.

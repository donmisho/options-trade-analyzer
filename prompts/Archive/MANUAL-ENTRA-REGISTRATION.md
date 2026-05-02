# OTA-460 — Entra Confidential Client Registration (Manual Step)

**Do this BEFORE running any Claude Code prompts.**

> **Note:** Your Entra tenant blocks client secrets via tenant-wide policy.
> We use a **certificate-based credential** instead — this is Microsoft's
> recommended approach and more secure (no secret rotation needed).

---

## Step 1: Register the App (DONE if you already completed this)

If you already registered "Options Trade Analyzer - BFF" as a Web app, skip to Step 2.

1. Go to [Azure Portal → Microsoft Entra ID → App registrations](https://portal.azure.com/#view/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/~/RegisteredApps)
2. Click **New registration**
3. Fill in:
   - **Name**: `Options Trade Analyzer - BFF`
   - **Supported account types**: Accounts in this organizational directory only
   - **Redirect URI**: Select **Web**, enter: `https://127.0.0.1:8000/api/v1/auth/entra/callback`
4. Click **Register**

## Step 2: Add the Production Redirect URI

1. In your app registration, go to **Authentication** (left sidebar)
2. Under **Web → Redirect URIs**, click **Add URI**
3. Enter: `https://oa.tmtctech.ai/api/v1/auth/entra/callback`
4. Click **Save**

You should now have two URIs listed under the Web platform:
- `https://127.0.0.1:8000/api/v1/auth/entra/callback`
- `https://oa.tmtctech.ai/api/v1/auth/entra/callback`

## Step 3: Note the IDs

From the app's **Overview** page, copy:
- **Application (client) ID** → you'll add this to `.env` as `ENTRA_CLIENT_ID`
- **Directory (tenant) ID** → you'll add this to `.env` as `ENTRA_TENANT_ID`

## Step 4: Generate a Certificate

Open PowerShell on your dev machine:

```powershell
# Create a self-signed certificate (2-year expiry)
$cert = New-SelfSignedCertificate `
    -Subject "CN=OTA-BFF-Auth" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -KeyExportPolicy Exportable `
    -KeySpec Signature `
    -KeyLength 2048 `
    -KeyAlgorithm RSA `
    -HashAlgorithm SHA256 `
    -NotAfter (Get-Date).AddYears(2)

# Export the public key (.cer) for Entra
Export-Certificate -Cert $cert -FilePath "$env:USERPROFILE\ota-bff.cer"

# Export the private key + cert (.pfx) for Key Vault
$pfxPassword = ConvertTo-SecureString -String "OtaBffCert2026!" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath "$env:USERPROFILE\ota-bff.pfx" -Password $pfxPassword

# Display the thumbprint (you'll need this to verify)
Write-Host "Certificate Thumbprint: $($cert.Thumbprint)"
```

**Save the thumbprint** — you'll need it for verification.

## Step 5: Upload Public Key to Entra

1. In your app registration, go to **Certificates & secrets** (left sidebar)
2. Click the **Certificates (0)** tab
3. Click **Upload certificate**
4. Browse to `%USERPROFILE%\ota-bff.cer`
5. Add a description: `OTA BFF Auth Certificate`
6. Click **Add**

You should see the certificate listed with its thumbprint matching what PowerShell displayed.

## Step 6: Store Private Key in Azure Key Vault

```powershell
# Import the .pfx into Key Vault as a certificate object
az keyvault certificate import `
    --vault-name "options-analyzer" `
    --name "entra-bff-cert" `
    --file "$env:USERPROFILE\ota-bff.pfx" `
    --password "OtaBffCert2026!"
```

Verify it's there:
```powershell
az keyvault certificate show `
    --vault-name "options-analyzer" `
    --name "entra-bff-cert" `
    --query "{name:name, thumbprint:x509ThumbprintHex, expires:attributes.expires}" `
    -o table
```

## Step 7: Add API Permissions

1. In your app registration, go to **API permissions** (left sidebar)
2. Click **Add a permission**
3. Select **Microsoft Graph** → **Delegated permissions**
4. Check: `openid`, `profile`, `email`, `User.Read`
5. Click **Add permissions**
6. Click **Grant admin consent for TM Technologies** (the blue button at the top)
7. Confirm

All four permissions should show a green checkmark under "Status."

## Step 8: Update .env

Add these to `options-analyzer/.env`:
```
ENTRA_CLIENT_ID=<application-client-id-from-step-3>
ENTRA_TENANT_ID=<directory-tenant-id-from-step-3>
ENTRA_CERT_THUMBPRINT=<thumbprint-from-step-4>
ENTRA_REDIRECT_URI_DEV=https://127.0.0.1:8000/api/v1/auth/entra/callback
ENTRA_REDIRECT_URI_PROD=https://oa.tmtctech.ai/api/v1/auth/entra/callback
```

## Step 9: Clean Up Local Files

After Key Vault import is confirmed:
```powershell
# Delete local certificate files (they're now safely in Key Vault and Entra)
Remove-Item "$env:USERPROFILE\ota-bff.cer"
Remove-Item "$env:USERPROFILE\ota-bff.pfx"
```

The private key also remains in your Windows certificate store (`Cert:\CurrentUser\My`). That's fine for dev — the App Service will pull from Key Vault in production.

## Step 10: Keep the Old SPA Registration

Do NOT delete the existing SPA app registration. Rename it in the portal to include `(DEPRECATED - rollback only)`. We'll remove it after the BFF migration is verified in production.

---

## Verification Checklist

- [ ] App registration exists with type **Web** (not SPA)
- [ ] Two redirect URIs listed under Web platform (dev + prod)
- [ ] Certificate uploaded and visible in Certificates tab with correct thumbprint
- [ ] Certificate imported into Key Vault (`entra-bff-cert`)
- [ ] API permissions: openid, profile, email, User.Read — all with admin consent
- [ ] `.env` updated with ENTRA_CLIENT_ID, ENTRA_TENANT_ID, ENTRA_CERT_THUMBPRINT
- [ ] Local .cer and .pfx files deleted

---

**After completing these steps**, proceed with the Claude Code prompts in order:
1. T1-BACKEND prompt (Terminal 1)
2. T2-FRONTEND prompt (Terminal 2) — can run in parallel with T1
3. T3-DOCS-AGENT prompt (Terminal 3) — run after T1 and T2 complete

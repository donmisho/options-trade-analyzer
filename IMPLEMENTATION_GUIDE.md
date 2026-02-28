# Phase 3a: Schwab Integration — Implementation Guide

## Overview

This guide walks you through every file you need to create or modify to connect
your Options Analyzer to Schwab's market data API. Follow the steps in order.

**What you'll have when done:**
- OAuth login flow — click a link, log into Schwab, get tokens stored
- Schwab market data adapter feeding your analysis engines
- Provider toggle — switch between Tradier and Schwab via .env
- Token auto-refresh (30-minute access tokens refresh silently)
- Status endpoint so the frontend knows if Schwab is connected

---

## Step 0: Generate SSL Certificate (One-Time Setup)

Schwab requires HTTPS for OAuth callbacks. You need a self-signed certificate
so your local FastAPI server can run on HTTPS.

### 0a. Open PowerShell in your project root

In VS Code, press **Ctrl+`** (backtick) to open the terminal. Make sure you're
in your project root:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
```

### 0b. Create a certs folder

```powershell
New-Item -ItemType Directory -Path "certs" -Force
```

### 0c. Generate the certificate using PowerShell

This creates a self-signed cert valid for 365 days. PowerShell has a built-in
command for this, so you don't need to install OpenSSL.

```powershell
$cert = New-SelfSignedCertificate `
    -DnsName "127.0.0.1","localhost" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -NotAfter (Get-Date).AddDays(365) `
    -FriendlyName "Options Analyzer Dev SSL"
```

### 0d. Export to PEM files (what uvicorn needs)

```powershell
# Export the certificate (public key)
$certPath = "certs\cert.pem"
$cert | Export-Certificate -FilePath "certs\cert.der" -Type CERT
certutil -encode "certs\cert.der" $certPath

# Export the private key
$password = ConvertTo-SecureString -String "devonly" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath "certs\cert.pfx" -Password $password

# Convert PFX to PEM key (requires openssl — see note below)
```

**IMPORTANT NOTE:** The PFX-to-PEM conversion needs OpenSSL. If you don't have
OpenSSL installed, here's an easier alternative that works with uvicorn:

### 0e. EASIER ALTERNATIVE — Use Python to generate the cert

This is simpler and doesn't require OpenSSL. Run this in your activated venv:

```powershell
venv\Scripts\activate
pip install cryptography --break-system-packages
python -c "
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime, ipaddress

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, u'127.0.0.1'),
])
cert = (x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
    .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
    .add_extension(x509.SubjectAlternativeName([
        x509.DNSName(u'localhost'),
        x509.IPAddress(ipaddress.IPv4Address(u'127.0.0.1')),
    ]), critical=False)
    .sign(key, hashes.SHA256()))

with open('certs/key.pem', 'wb') as f:
    f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
with open('certs/cert.pem', 'wb') as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))
print('Certificate created: certs/cert.pem and certs/key.pem')
"
```

### 0f. Add certs to .gitignore

You don't want SSL certs in your GitHub repo:

```powershell
Add-Content -Path ".gitignore" -Value "`ncerts/"
```

---

## Step 1: Install New Dependencies

```powershell
venv\Scripts\activate
pip install httpx cryptography --break-system-packages
```

You already have httpx (Tradier uses it), but this ensures it's there.
The `cryptography` package is for the SSL cert generation above.

Update requirements.txt:

```powershell
pip freeze > requirements.txt
```

---

## Step 2: Update .env File

Open `.env` in VS Code (it's in the `options-analyzer/` folder) and add
these lines at the bottom:

```env
# --- Schwab OAuth ---
SCHWAB_APP_KEY=PASTE_YOUR_APP_KEY_HERE
SCHWAB_APP_SECRET=PASTE_YOUR_APP_SECRET_HERE
SCHWAB_CALLBACK_URL=https://127.0.0.1:8000/api/v1/auth/schwab/callback

# --- Provider Selection ---
# Change this to "schwab" once you've completed the OAuth login
DEFAULT_MARKET_DATA_PROVIDER=tradier
```

**Replace `PASTE_YOUR_APP_KEY_HERE` and `PASTE_YOUR_APP_SECRET_HERE` with your
actual Schwab credentials from the Developer Portal.**

Also update `.env.example` with placeholders (no real secrets):

```env
# --- Schwab OAuth ---
SCHWAB_APP_KEY=your-schwab-app-key
SCHWAB_APP_SECRET=your-schwab-app-secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8000/api/v1/auth/schwab/callback
DEFAULT_MARKET_DATA_PROVIDER=tradier
```

---

## Step 3: Update config.py

**File:** `app/core/config.py`

Find the section that says `# --- Tradier (non-secret settings) ---` and add
the Schwab settings AFTER it. Your config.py should end up looking like this
(showing only the parts you're adding — don't delete anything):

**ADD these lines after the Tradier settings block:**

```python
    # --- Schwab (non-secret settings) ---
    # App key and secret can also come from SecretsManager / Key Vault
    # These .env values are the fallback for local dev
    schwab_app_key: Optional[str] = None
    schwab_app_secret: Optional[str] = None
    schwab_callback_url: str = "https://127.0.0.1:8000/api/v1/auth/schwab/callback"

    # --- SSL for local HTTPS (Schwab OAuth requires it) ---
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None
```

---

## Step 4: Create New Files

Create these 3 new files in the locations shown below.

### 4a. Token Manager → `app/providers/schwab_token_manager.py`

Copy the file `schwab_token_manager.py` from this package into:
`options-analyzer/app/providers/schwab_token_manager.py`

### 4b. Market Data Adapter → `app/providers/schwab.py`

Copy the file `schwab.py` from this package into:
`options-analyzer/app/providers/schwab.py`

### 4c. OAuth Routes → `app/api/schwab_auth_routes.py`

Copy the file `schwab_auth_routes.py` from this package into:
`options-analyzer/app/api/schwab_auth_routes.py`

**In VS Code:** Right-click the target folder in the Explorer sidebar →
"New File" → paste the filename → then paste the file contents.

---

## Step 5: Update factory.py (Register Schwab Provider)

**File:** `app/providers/factory.py`

### 5a. Add the import at the top

Find the line that imports TradierMarketData:

```python
from app.providers.tradier import TradierMarketData
```

Add this line right after it:

```python
from app.providers.schwab import SchwabMarketData
```

### 5b. Register Schwab in PROVIDER_REGISTRY

Find the commented-out Schwab placeholder in PROVIDER_REGISTRY (it says
`# "schwab" will be added in Phase 3`). Replace that entire comment block with:

```python
    "schwab": {
        "capabilities": ["market_data"],
        "market_data": None,  # Set at runtime by init — needs token_manager
    },
```

### 5c. Add Schwab initialization to ProviderFactory

The Schwab adapter needs the token_manager (unlike Tradier which just needs
a token string). Add this method to the ProviderFactory class, right after
the `__init__` method:

```python
    def init_schwab(self, token_manager):
        """
        Initialize the Schwab provider with its token manager.

        WHY separate init: The Schwab adapter needs the SchwabTokenManager,
        which is created in main.py at startup. Unlike Tradier where we can
        create the adapter from just a token string, Schwab needs the full
        token manager for auto-refresh. So we register the factory function
        here after the token manager exists.
        """
        from app.providers.schwab import SchwabMarketData

        self._schwab_token_manager = token_manager

        # Now update the registry with a real factory function
        if "schwab" in PROVIDER_REGISTRY:
            PROVIDER_REGISTRY["schwab"]["market_data"] = (
                lambda secrets, user_id, env: SchwabMarketData(token_manager)
            )
            logger.info("ProviderFactory: Schwab market data adapter registered")
```

---

## Step 6: Update main.py (Wire Everything Together)

**File:** `app/main.py`

### 6a. Add imports

Find the import block at the top. Add these new imports:

```python
from app.api.schwab_auth_routes import router as schwab_auth_router, init_schwab_auth_routes
from app.providers.schwab_token_manager import SchwabTokenManager
```

### 6b. Update the lifespan function

In the `lifespan` function, find the line that says:

```python
    # 4. Initialize provider factory
```

ADD these lines right AFTER the provider factory initialization block
(after `init_analysis_routes(provider_factory)`) but BEFORE the
`logger.info(f"{settings.app_name} ready..."` line:

```python
    # 5. Initialize Schwab OAuth token manager
    schwab_token_manager = SchwabTokenManager(secrets_manager)
    init_schwab_auth_routes(schwab_token_manager)
    provider_factory.init_schwab(schwab_token_manager)
    logger.info("Schwab OAuth token manager initialized")
```

### 6c. Add the router

Find the section with `# --- ROUTES ---` and add this line with the others:

```python
app.include_router(schwab_auth_router, prefix="/api/v1")
```

### 6d. Update CORS for HTTPS

Find the CORS middleware block. Update `allow_origins` to include the HTTPS
variant (your browser will be on HTTPS now):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://localhost:5173",
        "https://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Step 7: Test It

### 7a. Start the backend with HTTPS

Instead of the normal uvicorn command, use this one that enables SSL:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem
```

**IMPORTANT:** Your backend is now at `https://127.0.0.1:8000` (HTTPS, not HTTP).

### 7b. Verify it starts

Open your browser and go to:

```
https://127.0.0.1:8000/docs
```

Your browser will warn about the self-signed certificate — click "Advanced" →
"Proceed to 127.0.0.1 (unsafe)". This is expected and safe for local dev.

You should see the Swagger docs with the new Schwab OAuth endpoints.

### 7c. Check Schwab status

In Swagger docs, try the `GET /api/v1/auth/schwab/status` endpoint.
It should return:

```json
{
  "connected": false,
  "needs_reauth": true,
  "access_token_valid": false,
  ...
}
```

### 7d. Connect Schwab

Open this URL in your browser:

```
https://127.0.0.1:8000/api/v1/auth/schwab/login
```

This will redirect you to Schwab's login page. Log in with your **brokerage
credentials** (not Developer Portal), authorize the app, and Schwab will
redirect back. You should see a green "Connected Successfully!" page.

### 7e. Verify connection

Go back to Swagger docs and check status again. Now it should show:

```json
{
  "connected": true,
  "access_token_valid": true,
  "access_token_expires_in_seconds": ~1800,
  "refresh_token_valid": true,
  "refresh_token_expires_in_seconds": ~604800,
  "needs_reauth": false
}
```

### 7f. Test a quote

In Swagger docs, try the `GET /api/v1/market/quote?symbol=TSLA` endpoint.
If you've switched your .env to `DEFAULT_MARKET_DATA_PROVIDER=schwab`, it
should return live data from Schwab.

---

## Step 8: Switch Provider to Schwab

Once you've verified the OAuth connection works:

1. Open `.env`
2. Change `DEFAULT_MARKET_DATA_PROVIDER=tradier` to `DEFAULT_MARKET_DATA_PROVIDER=schwab`
3. Save — uvicorn auto-reloads
4. Test the analysis endpoints — they should now use Schwab data

---

## Step 9: Update Frontend API Base URL

Since the backend is now HTTPS, update the frontend's API client.

**File:** `web/src/api/client.js` (or wherever your base URL is configured)

Change:
```javascript
const API_BASE = "http://localhost:8000/api/v1";
```

To:
```javascript
const API_BASE = "https://127.0.0.1:8000/api/v1";
```

---

## Azure Key Vault Secret Names

When you deploy to Azure, these secrets go in Key Vault instead of .env:

| Key Vault Secret Name    | What It Stores                          |
|--------------------------|-----------------------------------------|
| `schwab-app-key`         | Your Schwab App Key                     |
| `schwab-app-secret`      | Your Schwab App Secret                  |
| `schwab-token-data`      | JSON blob with access + refresh tokens  |

The `schwab-token-data` secret is written automatically by the token manager
when you authenticate. You don't need to set it manually.

For Azure deployment, also set these in App Service Configuration:
- `SCHWAB_CALLBACK_URL` = `https://options-analyzer-api.azurewebsites.net/api/v1/auth/schwab/callback`
- `DEFAULT_MARKET_DATA_PROVIDER` = `schwab`

---

## What's Next

After this session is working:
- **Session 2:** Test all three analysis screens with Schwab data during market hours
- **Session 3:** Interactive config panels with sliders, watchlist price wiring
- **Azure deployment:** Deploy with Key Vault secrets, test OAuth on production URL

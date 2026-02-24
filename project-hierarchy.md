# Options Analyzer — VS Code Project Hierarchy

```
Options Analyzer/                          ← Your VS Code workspace root
│
├── options-analyzer/                      ← The FastAPI backend (EXISTING)
│   ├── venv/                              ← Python virtual environment (don't touch)
│   ├── .env                               ← Your secrets (Tradier token, JWT key)
│   ├── .env.example                       ← Template for .env
│   ├── requirements.txt                   ← Python dependencies
│   ├── README.md                          ← Project documentation
│   ├── options_analyzer.db                ← SQLite database (auto-created)
│   │
│   └── app/                               ← All Python code lives here
│       ├── main.py                        ← FastAPI entry point ⚡ EDIT THIS (add 3 lines)
│       │
│       ├── core/                          ← EXISTING — config & secrets
│       │   ├── config.py                  ← App settings (loads from .env)
│       │   └── secrets.py                 ← SecretsManager (Key Vault + .env fallback)
│       │
│       ├── auth/                          ← EXISTING — authentication
│       │   ├── service.py                 ← Password hashing, JWT, TOTP
│       │   └── dependencies.py            ← Auth middleware (Tier 1/2/3)
│       │
│       ├── models/                        ← EXISTING — data models
│       │   ├── database.py                ← SQLAlchemy models
│       │   ├── session.py                 ← Async DB engine
│       │   └── schemas.py                 ← Pydantic request/response schemas
│       │
│       ├── providers/                     ← EXISTING — API adapters
│       │   ├── base.py                    ← Abstract interfaces
│       │   ├── tradier.py                 ← Tradier API adapter
│       │   └── factory.py                 ← Creates provider instances
│       │
│       ├── analysis/                      ← 🆕 NEW — copy entire folder from package
│       │   ├── __init__.py                ← 🆕 Package exports
│       │   ├── vertical_engine.py         ← 🆕 Vertical spread scorer
│       │   ├── long_call_engine.py        ← 🆕 Long call scorer
│       │   └── directional_engine.py      ← 🆕 Strategy comparator
│       │
│       └── api/                           ← API routes
│           ├── auth_routes.py             ← EXISTING — login, register, MFA
│           ├── market_routes.py           ← EXISTING — quotes, chains
│           ├── config_routes.py           ← EXISTING — user preferences
│           └── analysis_routes.py         ← 🆕 NEW — copy this file
│
│
└── web/                                   ← 🆕 NEW — React frontend (create with npm)
    ├── node_modules/                      ← Auto-created by npm install (don't touch)
    ├── package.json                       ← Auto-created by create-react-app
    ├── public/
    │   └── index.html                     ← Auto-created
    │
    └── src/                               ← Your React code
        ├── index.js                       ← Auto-created entry point
        ├── App.jsx                        ← Main app with routing (build later)
        │
        ├── api/                           ← 🆕 Copy from package
        │   └── client.js                  ← 🆕 API bridge (talks to FastAPI)
        │
        ├── components/                    ← Shared UI components (build later)
        │   ├── Layout.jsx                 ← Sidebar nav + top bar
        │   ├── Chart.jsx                  ← TOS-style candlestick chart
        │   └── shared.jsx                 ← Badges, buttons, metric cards
        │
        └── pages/                         ← One file per screen
            ├── Dashboard.jsx              ← (build later)
            ├── Chain.jsx                  ← (build later)
            ├── Analysis.jsx               ← 🆕 Copy from package — connected to API
            ├── Portfolio.jsx              ← (build later)
            ├── Trade.jsx                  ← (build later)
            └── Settings.jsx               ← (build later)
```

## What to do RIGHT NOW (in order)

### Step 1: Copy backend files
```
From package:  backend/app/analysis/       →  options-analyzer/app/analysis/
From package:  backend/app/api/analysis_routes.py  →  options-analyzer/app/api/analysis_routes.py
```

### Step 2: Edit main.py (3 lines)
```python
# ADD this import near the top with the other route imports:
from app.api.analysis_routes import router as analysis_router, init_analysis_routes

# ADD this line where provider factory is initialized:
init_analysis_routes(provider_factory)

# ADD this line where other routers are included:
app.include_router(analysis_router, prefix="/api/v1")
```

### Step 3: Test backend
```bash
cd options-analyzer
venv\Scripts\activate
uvicorn app.main:app --reload
# Go to http://localhost:8000/docs → you should see 3 new analysis endpoints
```

### Step 4: Create React project (separate terminal)
```bash
cd "Options Analyzer"
npx create-react-app web
cd web
npm install react-router-dom axios
```

### Step 5: Copy frontend files
```
From package:  frontend/src/api/client.js      →  web/src/api/client.js
From package:  frontend/src/pages/Analysis.jsx  →  web/src/pages/Analysis.jsx
```

### Step 6: Add CORS to main.py
```python
from fastapi.middleware.cors import CORSMiddleware

# Add BEFORE route registrations:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Step 7: Run both (two separate terminals)

**Terminal 1 — API (port 8000):**
```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
venv\Scripts\activate
uvicorn app.main:app --reload
```

**Terminal 2 — React (port 5173):**
```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer\web"
npm run dev
```



### Future Enhancements:
```
** Config Screen (future): Build a UI config screen for all analysis parameters. Vertical spread filters are in UserConfig in models.py (already DB-backed). Long call filters are hardcoded in LongCallFilters in app/analysis/long_call_engine.py and need to be wired into the user config system first. **
```

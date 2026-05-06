# Development Environment

**Last Updated:** 2026-05-06 UTC
**Governing Story:** OTA-582 (Documentation Governance — Project)
**Initial creation Subtask:** OTA-587

---

Local development setup and troubleshooting for OTA. The "how to run OTA on your machine" reference. Read this when setting up the project for the first time or troubleshooting an environment issue.

## Project root

```
C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer
```

Always include the full `cd` command in Claude Code prompts. Don's working directory in shell sessions is not assumed.

## Backend (FastAPI)

### One-time setup

```powershell
python -m venv venv
venv\Scripts\activate          # Windows (PowerShell)
# source venv/bin/activate     # Unix
pip install -r requirements.txt
```

The venv directory is **`venv` (not `.venv`)**. Always include the full `cd` and `activate` commands in Claude Code prompts so the right interpreter is used.

### Run with HTTPS

```powershell
uvicorn app.main:app --reload --ssl-keyfile=key.pem --ssl-certfile=cert.pem --host=127.0.0.1 --port=8000
```

HTTPS is required for Schwab OAuth and for dev parity with prod.

- API docs: `https://127.0.0.1:8000/docs`
- Health: `https://127.0.0.1:8000/health`

### Self-signed cert generation

Use Python's `cryptography` library, **not** the OpenSSL CLI. PowerShell on Windows handles backtick line continuation poorly with OpenSSL, and the resulting commands silently produce invalid certs.

A scripted cert generator using `cryptography` is the canonical approach. Do not introduce OpenSSL CLI commands into any prompt or script.

## Frontend (React + Vite)

```powershell
cd web
npm install
npm run dev     # Vite dev server (HTTPS) with proxy to FastAPI backend
npm run build   # Production build
npm run lint    # ESLint
```

The Vite dev server runs on `https://localhost:5173` and proxies `/api` requests to `https://127.0.0.1:8000`. Both use self-signed certificates in development.

## Testing

```powershell
pytest                          # All tests
pytest tests/test_something.py  # Specific file
pytest --cov=app                # With coverage
```

Test infrastructure today is minimal — most validation happens via Swagger UI at `/docs`. Auth, provider, and route coverage is a known gap tracked under the Architecture Optimization Epic.

## Zombie Process Warning (Windows)

**Before restarting the backend, always kill existing Python and uvicorn processes first:**

```powershell
Get-Process python,uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force
netstat -ano | findstr ":8000"
```

Windows does not always release port 8000 cleanly. A zombie uvicorn process will answer requests silently, making new route registrations invisible and causing confusing 404s.

**Symptom checklist** — if any of these are happening, suspect a zombie:

- A new route returns 404 even though the code is correct
- API responses look stale (old behavior reappears after a code change)
- The browser shows the old SPA bundle even after `npm run build`
- `uvicorn --reload` claims to restart but route changes don't take effect

Run the kill command, confirm `netstat` shows no listener on 8000, then restart cleanly.

## IDE conventions

VS Code is the assumed editor. Don is comfortable navigating VS Code — Claude Code prompts skip basic editor coaching and focus on environment issues (Python, dependencies, ports, certs).

## Troubleshooting quick reference

| Symptom | Likely cause | Resolution |
|---|---|---|
| 404 on a new route | Zombie uvicorn process | `Stop-Process` cycle (above) |
| HTTPS cert errors in browser | Self-signed cert not trusted | Browser-level trust acceptance, or regenerate via Python `cryptography` script |
| `pip install` fails on a package | Wrong Python version active | `where python` (Windows) — confirm venv is activated |
| Vite proxy not forwarding `/api` | Backend not running on port 8000 | Verify backend is listening (`netstat`) and HTTPS cert is valid |
| Schwab API returns 401 in dev | Token expired or cert mismatch | See `SCHWAB-LOGIN-PROCESS.md` for the OAuth refresh flow |

---

## Change Log

| Date | Subtask | Change |
|---|---|---|
| 2026-05-06 UTC | OTA-587 | Initial creation. Content ported from `CLAUDE.md` (Development Environment + Zombie Process Warning sections) as part of the Documentation Governance restructure. After this file lands, the corresponding section in CLAUDE.md becomes a one-line pointer. |

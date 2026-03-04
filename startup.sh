#!/bin/bash
# Azure App Service startup script
# Installs ODBC Driver 18 for SQL Server (missing from base Python container image)
# then launches the FastAPI app.
#
# NOTE: This runs as root in the App Service container.

# ── Find Python from Oryx virtual environment ─────────────────────────────────
# Oryx may use different venv paths depending on version. Try them in order.
PYTHON=""
for CANDIDATE in \
    /home/site/wwwroot/antenv/bin/python3 \
    /home/site/wwwroot/antenv/bin/python \
    /home/site/wwwroot/.venv/bin/python3 \
    /home/site/wwwroot/.venv/bin/python; do
    if [ -x "$CANDIDATE" ]; then
        PYTHON="$CANDIDATE"
        break
    fi
done

# If no Oryx venv found, fall back to system Python (App Service ensures PATH has it)
if [ -z "$PYTHON" ]; then
    PYTHON=$(command -v python3 || command -v python || echo "")
fi

echo "[startup.sh] Python: ${PYTHON:-NOT FOUND}"

# ── Install ODBC Driver 18 if missing ────────────────────────────────────────
ODBC18_LIB_DIR="/opt/microsoft/msodbcsql18/lib64"
if ls "${ODBC18_LIB_DIR}"/libmsodbcsql-18*.so.* >/dev/null 2>&1; then
    echo "[startup.sh] ODBC Driver 18 already present."
else
    echo "[startup.sh] Installing ODBC Driver 18 for SQL Server..."

    # Microsoft signing key
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        -o /etc/apt/trusted.gpg.d/microsoft.asc 2>/dev/null \
        || curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
            | apt-key add - 2>/dev/null \
        || echo "[startup.sh] Warning: could not add Microsoft signing key"

    # Pick the right repo config (Debian vs Ubuntu)
    if [ -f /etc/debian_version ]; then
        DEB_VER=$(cut -d. -f1 < /etc/debian_version)
        REPO_URL="https://packages.microsoft.com/config/debian/${DEB_VER}/prod.list"
    else
        UBUNTU_VER=$(lsb_release -rs 2>/dev/null || echo "22.04")
        REPO_URL="https://packages.microsoft.com/config/ubuntu/${UBUNTU_VER}/prod.list"
    fi

    curl -fsSL "$REPO_URL" -o /etc/apt/sources.list.d/mssql-release.list 2>/dev/null \
        || echo "[startup.sh] Warning: could not add Microsoft repo"

    apt-get update -qq 2>/dev/null || echo "[startup.sh] Warning: apt-get update failed"
    ACCEPT_EULA=Y apt-get install -y -qq msodbcsql18 2>/dev/null \
        && echo "[startup.sh] ODBC Driver 18 installed." \
        || echo "[startup.sh] Warning: ODBC Driver 18 install failed — Azure SQL may not work."
fi

# ── Start the app ─────────────────────────────────────────────────────────────
if [ -z "$PYTHON" ]; then
    echo "[startup.sh] ERROR: No Python found. Cannot start uvicorn."
    exit 1
fi

echo "[startup.sh] Starting: ${PYTHON} -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
cd /home/site/wwwroot
exec "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000

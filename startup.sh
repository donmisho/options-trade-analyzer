#!/bin/bash
# Azure App Service startup script — runs as root before uvicorn.
# Installs ODBC Driver 18 for SQL Server (not in base Python container image)
# then launches the FastAPI app via the Oryx virtual environment.

set -e

ODBC18_LIB_DIR="/opt/microsoft/msodbcsql18/lib64"
ANTENV="/home/site/wwwroot/antenv"
PYTHON="${ANTENV}/bin/python"

# ── Install ODBC Driver 18 if missing ────────────────────────────────────────
if ! ls "${ODBC18_LIB_DIR}"/libmsodbcsql-18*.so.* 2>/dev/null | grep -q .; then
    echo "[startup.sh] ODBC Driver 18 not found — installing..."

    {
        # Microsoft signing key
        curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
            -o /etc/apt/trusted.gpg.d/microsoft.asc

        # Detect OS family and pick the correct Microsoft package list
        if [ -f /etc/debian_version ]; then
            DEB_VER=$(cut -d. -f1 < /etc/debian_version)
            curl -fsSL "https://packages.microsoft.com/config/debian/${DEB_VER}/prod.list" \
                -o /etc/apt/sources.list.d/mssql-release.list
        else
            UBUNTU_VER=$(lsb_release -rs 2>/dev/null || echo "22.04")
            curl -fsSL "https://packages.microsoft.com/config/ubuntu/${UBUNTU_VER}/prod.list" \
                -o /etc/apt/sources.list.d/mssql-release.list
        fi

        apt-get update -qq
        ACCEPT_EULA=Y apt-get install -y -qq msodbcsql18
        echo "[startup.sh] ODBC Driver 18 installed."
    } || echo "[startup.sh] WARNING: ODBC Driver 18 install failed — app will start but Azure SQL may not connect."
else
    echo "[startup.sh] ODBC Driver 18 already present."
fi

# ── Start the app ─────────────────────────────────────────────────────────────
echo "[startup.sh] Starting uvicorn via ${PYTHON}..."
exec "${PYTHON}" -m uvicorn app.main:app --host 0.0.0.0 --port 8000

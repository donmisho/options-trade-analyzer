#!/bin/bash
# Azure App Service startup script
# Installs ODBC Driver 18 for SQL Server (missing from base Python container image)
# then launches the FastAPI app.
#
# NOTE: This script runs as root in the App Service container.

# Tee all output to a persistent log file (readable via az webapp log download)
mkdir -p /home/LogFiles
exec > >(tee /home/LogFiles/startup_debug.log) 2>&1

echo "[startup.sh] === BEGIN ==="
echo "[startup.sh] whoami=$(whoami 2>/dev/null || echo unknown)"
echo "[startup.sh] PATH=$PATH"

# ── Show filesystem to diagnose Python / venv location ───────────────────────
echo "[startup.sh] /home/site/wwwroot/ contents:"
ls -la /home/site/wwwroot/ 2>&1 | head -25

echo "[startup.sh] Looking for virtual environments..."
for VENV_DIR in /home/site/wwwroot/antenv /home/site/wwwroot/.venv; do
    if [ -f "${VENV_DIR}/bin/python3" ] || [ -f "${VENV_DIR}/bin/python" ]; then
        echo "[startup.sh] Found venv at: ${VENV_DIR}"
    else
        echo "[startup.sh] Not found: ${VENV_DIR}"
    fi
done

# ── Activate Oryx virtual environment ────────────────────────────────────────
VENV_ACTIVATED=false
for VENV in /home/site/wwwroot/antenv /home/site/wwwroot/.venv; do
    if [ -f "${VENV}/bin/activate" ]; then
        . "${VENV}/bin/activate"
        VENV_ACTIVATED=true
        echo "[startup.sh] Activated venv: ${VENV}"
        break
    fi
done

if [ "$VENV_ACTIVATED" = "false" ]; then
    echo "[startup.sh] No Oryx venv found, using PATH Python"
fi

PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo "")
echo "[startup.sh] Python: ${PYTHON} ($(${PYTHON} --version 2>&1))"

# ── Install ODBC Driver 18 if missing ────────────────────────────────────────
ODBC18_LIB_DIR="/opt/microsoft/msodbcsql18/lib64"
if ls "${ODBC18_LIB_DIR}"/libmsodbcsql-18*.so.* >/dev/null 2>&1; then
    echo "[startup.sh] ODBC Driver 18 already present."
else
    echo "[startup.sh] Installing ODBC Driver 18..."

    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        -o /etc/apt/trusted.gpg.d/microsoft.asc 2>/dev/null \
        && echo "[startup.sh] MS key OK" \
        || echo "[startup.sh] Warning: MS key curl failed, trying apt-key"

    if [ -f /etc/debian_version ]; then
        DEB_VER=$(cut -d. -f1 < /etc/debian_version)
        REPO_URL="https://packages.microsoft.com/config/debian/${DEB_VER}/prod.list"
        echo "[startup.sh] Detected Debian ${DEB_VER}"
    else
        UBUNTU_VER=$(lsb_release -rs 2>/dev/null || echo "22.04")
        REPO_URL="https://packages.microsoft.com/config/ubuntu/${UBUNTU_VER}/prod.list"
        echo "[startup.sh] Detected Ubuntu ${UBUNTU_VER}"
    fi

    curl -fsSL "$REPO_URL" -o /etc/apt/sources.list.d/mssql-release.list 2>/dev/null \
        && echo "[startup.sh] Repo list OK" \
        || echo "[startup.sh] Warning: repo list curl failed"

    apt-get update -qq 2>/dev/null \
        && echo "[startup.sh] apt-get update OK" \
        || echo "[startup.sh] Warning: apt-get update failed"

    ACCEPT_EULA=Y apt-get install -y -qq msodbcsql18 2>/dev/null \
        && echo "[startup.sh] ODBC Driver 18 installed OK" \
        || echo "[startup.sh] Warning: ODBC Driver 18 install failed"
fi

# ── Start the app ─────────────────────────────────────────────────────────────
if [ -z "$PYTHON" ]; then
    echo "[startup.sh] FATAL: No Python found."
    exit 1
fi

echo "[startup.sh] Starting uvicorn..."
cd /home/site/wwwroot
exec "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000

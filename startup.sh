#!/bin/bash
# Azure App Service startup script
# Installs ODBC Driver 18 for SQL Server (not in base App Service Python image),
# then starts uvicorn using the Python that App Service has already placed on PATH.

LOG="/tmp/startup.log"
echo "[startup.sh] === BEGIN $(date) ===" > "$LOG"
echo "USER: $(id 2>&1)" >> "$LOG"
echo "PATH: $PATH" >> "$LOG"
echo "VIRTUAL_ENV: ${VIRTUAL_ENV:-not set}" >> "$LOG"
echo "PYTHON: $(which python python3 2>&1)" >> "$LOG"
echo "PYTHONPATH: ${PYTHONPATH:-not set}" >> "$LOG"
echo "" >> "$LOG"
echo "=== /home/site/wwwroot/ ===" >> "$LOG"
ls -la /home/site/wwwroot/ >> "$LOG" 2>&1
echo "" >> "$LOG"
echo "=== antenv/bin/ ===" >> "$LOG"
ls /home/site/wwwroot/antenv/bin/ >> "$LOG" 2>&1

# ── Install ODBC Driver 18 for SQL Server ────────────────────────────────────
ODBC18_LIB_DIR="/opt/microsoft/msodbcsql18/lib64"
if ls "${ODBC18_LIB_DIR}"/libmsodbcsql-18*.so.* >/dev/null 2>&1; then
    echo "" >> "$LOG"
    echo "ODBC Driver 18: already installed" >> "$LOG"
else
    echo "" >> "$LOG"
    echo "ODBC Driver 18: installing..." >> "$LOG"

    # Microsoft signing key
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        -o /etc/apt/trusted.gpg.d/microsoft.asc 2>>"$LOG" && \
        echo "MS key: OK" >> "$LOG" || \
        echo "MS key: failed (curl error $?)" >> "$LOG"

    # Microsoft apt repo for the right OS
    if [ -f /etc/debian_version ]; then
        DEB_VER=$(cut -d. -f1 < /etc/debian_version)
        echo "OS: Debian ${DEB_VER}" >> "$LOG"
        curl -fsSL "https://packages.microsoft.com/config/debian/${DEB_VER}/prod.list" \
            -o /etc/apt/sources.list.d/mssql-release.list 2>>"$LOG" && \
            echo "MS repo list: OK" >> "$LOG" || \
            echo "MS repo list: failed" >> "$LOG"
    else
        UBUNTU_VER=$(lsb_release -rs 2>/dev/null || echo "22.04")
        echo "OS: Ubuntu ${UBUNTU_VER}" >> "$LOG"
        curl -fsSL "https://packages.microsoft.com/config/ubuntu/${UBUNTU_VER}/prod.list" \
            -o /etc/apt/sources.list.d/mssql-release.list 2>>"$LOG" && \
            echo "MS repo list: OK" >> "$LOG" || \
            echo "MS repo list: failed" >> "$LOG"
    fi

    apt-get update -qq >>"$LOG" 2>&1 && \
        echo "apt-get update: OK" >> "$LOG" || \
        echo "apt-get update: failed ($?)" >> "$LOG"

    ACCEPT_EULA=Y apt-get install -y -qq msodbcsql18 >>"$LOG" 2>&1 && \
        echo "msodbcsql18 install: OK" >> "$LOG" || \
        echo "msodbcsql18 install: failed ($?)" >> "$LOG"
fi

echo "" >> "$LOG"
echo "=== Python version ===" >> "$LOG"
python --version >> "$LOG" 2>&1
python3 --version >> "$LOG" 2>&1

echo "" >> "$LOG"
echo "=== Starting uvicorn ===" >> "$LOG"

# Copy log to persistent storage so it appears in az webapp log download
mkdir -p /home/LogFiles 2>/dev/null
cp "$LOG" /home/LogFiles/startup_debug.log 2>/dev/null || true

# App Service sets up PATH with the venv Python before running this script
cd /home/site/wwwroot
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

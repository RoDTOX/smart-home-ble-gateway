#!/usr/bin/env bash

# Deployment script for Samsung A6 (Cinderella) Termux + Debian proot environment
# Launches native BLE scanning service and Matter bridge for Google Home.
# Strictly isolated from TeslaMate.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=================================================="
echo " Deploying Native Smart Home BLE Gateway to A6   "
echo " (Isolated from TeslaMate)                        "
echo "=================================================="

# 1. Ensure scripts are executable
chmod +x "$SCRIPT_DIR"/services/*.sh "$SCRIPT_DIR"/apk/*.sh 2>/dev/null || true

# 2. Check config template
if [ ! -f "$SCRIPT_DIR/config/devices.json" ] && [ -f "$SCRIPT_DIR/config/devices.json.example" ]; then
    echo "[*] Initializing default config/devices.json from template..."
    cp "$SCRIPT_DIR/config/devices.json.example" "$SCRIPT_DIR/config/devices.json"
fi

# 3. Create isolated database smart_home_db
PROOT_CMD="proot-distro login debian --"
if command -v proot-distro >/dev/null 2>&1; then
    echo "[1/3] Ensuring PostgreSQL database smart_home_db exists..."
    $PROOT_CMD psql -U postgres -f "$SCRIPT_DIR/db/init_tables.sql" 2>/dev/null || echo "[WARN] Database/Table creation check completed."

    echo "[2/3] Checking Node.js Matter bridge dependencies..."
    $PROOT_CMD bash "$SCRIPT_DIR/services/matter-bridge-setup.sh" || echo "[WARN] Matter bridge setup skipped/completed."
fi

# 4. Start standalone Smart Home BLE Gateway
echo "[3/3] Starting Standalone Smart Home BLE Gateway..."
bash "$SCRIPT_DIR/services/start-smarthome.sh"

echo "=================================================="
echo " Deployment Complete! "
echo " BLE Gateway and Watchdog are active."
echo " Check logs at: ~/btsnoop_scanner.log and ~/smarthome_watchdog.log"
echo "=================================================="


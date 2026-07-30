#!/usr/bin/env bash

# Deployment script for Samsung A6 (Cinderella) Debian proot environment
# Launches native BLE scanning service and Matter bridge for Google Home.
# Strictly isolated from TeslaMate.

set -euo pipefail

echo "=================================================="
echo " Deploying Native Smart Home BLE Gateway to A6   "
echo " (Isolated from TeslaMate)                        "
echo "=================================================="

PROOT_CMD="proot-distro login debian --"

echo "[1/3] Creating isolated PostgreSQL database smart_home_db..."
$PROOT_CMD psql -U postgres -f "$(dirname "$0")/db/init_tables.sql" || echo "[WARN] Table/Database creation check completed."

echo "[2/3] Installing Python BLE & Matter dependencies..."
chmod +x "$(dirname "$0")/services/matter-bridge-setup.sh"
$PROOT_CMD bash "$(dirname "$0")/services/matter-bridge-setup.sh"

echo "[3/3] Starting Native BLE Scanner Daemon in background..."
$PROOT_CMD nohup python3 "$(dirname "$0")/services/ble_scanner.py" > /tmp/smart_home_ble_scanner.log 2>&1 &

echo "=================================================="
echo " Deployment Complete! "
echo " BLE Scanner running in background on A6."
echo " Log file: /tmp/smart_home_ble_scanner.log"
echo "=================================================="

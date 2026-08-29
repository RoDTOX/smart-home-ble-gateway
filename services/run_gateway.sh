#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# Smart Home BLE Gateway - Daemon Launcher
# Starts btsnoop_scanner.py (root) and db_logger.py (termux user)
# Log rotation (5MB x 2) is handled internally by Python RotatingFileHandler.
# ==============================================================================

GATEWAY_DIR="/data/data/com.termux/files/home/smart-home-ble-gateway"
[ ! -d "$GATEWAY_DIR" ] && GATEWAY_DIR="$HOME/smart-home-ble-gateway"

# 1. Clean up existing daemon instances
pkill -9 -f btsnoop_scanner.py 2>/dev/null || true
pkill -9 -f db_logger.py 2>/dev/null || true
sleep 1

# 2. Launch PostgreSQL Logger Daemon (Termux User)
nohup python3 -u "$GATEWAY_DIR/services/db_logger.py" > /dev/null 2>&1 &

# 3. Launch BTSnoop HCI Engine (Root required for /data/log/bt/btsnoop_hci.log)
su -c "nohup /data/data/com.termux/files/usr/bin/python3 -u $GATEWAY_DIR/services/btsnoop_scanner.py > /dev/null 2>&1 &"

echo "[OK] BLE Gateway Daemons Started (db_logger.py & btsnoop_scanner.py)."


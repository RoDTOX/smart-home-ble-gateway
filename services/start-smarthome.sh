#!/data/data/com.termux/files/usr/bin/bash

# ==============================================================================
# SMART HOME BLE GATEWAY - MASTER STANDALONE STARTUP SCRIPT
# Target: Samsung Galaxy A6 ("Cinderella", Android 9, Rooted Magisk)
# Completely isolated from TeslaMate.
# ==============================================================================

GATEWAY_DIR="/data/data/com.termux/files/home/smart-home-ble-gateway"
[ ! -d "$GATEWAY_DIR" ] && GATEWAY_DIR="$HOME/smart-home-ble-gateway"

BOOT_TIME=$(date '+%d-%m-%Y %H:%M:%S')

echo "=========================================="
echo "   SMART HOME BLE GATEWAY: STARTUP        "
echo "   TIMESTAMP: $BOOT_TIME                  "
echo "=========================================="

# --- 1. SYSTEM OPTIMIZATION (ROOT & WAKELOCK) ---
echo "[1/5] Configuring system power policies..."
# Keep CPU alive
termux-wake-lock > /dev/null 2>&1
echo "  [OK] Termux WakeLock active."

# Disable Android Doze Mode
su -c "dumpsys deviceidle disable" > /dev/null 2>&1
echo "  [OK] Android Doze Mode disabled."

# --- 2. HARDWARE BLUETOOTH CHECK ---
echo "[2/5] Checking Bluetooth hardware state..."
BT_STATE=$(su -c "settings get global bluetooth_on" 2>/dev/null | tr -d '\r\n')
if [ "$BT_STATE" != "1" ]; then
    echo "  [!] Bluetooth is OFF. Enabling Bluetooth via root..."
    su -c "svc bluetooth enable" > /dev/null 2>&1
    sleep 3
    echo "  [OK] Bluetooth enabled."
else
    echo "  [OK] Bluetooth is ON."
fi

# --- 3. PROCESS CLEANUP ---
echo "[3/5] Cleaning up old Smart Home processes..."
pkill -f smarthome_watchdog.sh 2>/dev/null || true
su -c "pkill -9 -f btsnoop_scanner.py 2>/dev/null || true"
pkill -9 -f db_logger.py 2>/dev/null || true
sleep 1
echo "  [OK] Stale processes cleaned."

# --- 4. LAUNCH FOREGROUND APK HELPER & DAEMONS ---
echo "[4/5] Launching BLE Foreground Scanner APK & Daemons..."
# Start Foreground Service APK (keeps BluetoothLeScanner alive with screen off)
su -c "am start -n com.smarthome.ble/.MainActivity" > /dev/null 2>&1
sleep 2

# Launch Python Daemons
bash "$GATEWAY_DIR/services/run_gateway.sh"

# --- 5. LAUNCH INDEPENDENT WATCHDOG ---
echo "[5/5] Launching Dedicated Smart Home Watchdog..."
if [ -f "$GATEWAY_DIR/services/smarthome_watchdog.sh" ]; then
    chmod +x "$GATEWAY_DIR/services/smarthome_watchdog.sh"
    nohup "$GATEWAY_DIR/services/smarthome_watchdog.sh" > /dev/null 2>&1 &
    echo "  [OK] smarthome_watchdog.sh running in background."
fi

echo "=========================================="
echo " SMART HOME BLE GATEWAY IS ONLINE!       "
echo " Logs:                                    "
echo "   - $HOME/btsnoop_scanner.log (max 5MB)  "
echo "   - $HOME/db_logger.log (max 5MB)        "
echo "   - $HOME/smarthome_watchdog.log         "
echo "=========================================="

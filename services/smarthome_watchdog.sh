#!/data/data/com.termux/files/usr/bin/bash

# ==============================================================================
# SMART HOME BLE GATEWAY - AUTONOMOUS WATCHDOG & SELF-HEALING GUARDIAN v2.0
# Target: Samsung Galaxy A6 (Android 9 / Rooted Magisk)
# Supervised: Bluetooth, WakeLock, BLE Foreground APK, btsnoop_scanner, db_logger, MQTT, PostgreSQL
# Features: Exponential Backoff (5 min delay after 3 failures), Log Rotation Safeguard
# ==============================================================================

GATEWAY_DIR="/data/data/com.termux/files/home/smart-home-ble-gateway"
[ ! -d "$GATEWAY_DIR" ] && GATEWAY_DIR="$HOME/smart-home-ble-gateway"

LOG_FILE="$HOME/smarthome_watchdog.log"
FAIL_COUNT_GATEWAY=0
CYCLE_COUNT=0
MAX_LOG_SIZE=$((5 * 1024 * 1024)) # 5MB

log_msg() {
    local MSG="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$MSG"
    echo "$MSG" >> "$LOG_FILE"
}

# Rotate watchdog log if larger than 2MB
rotate_watchdog_log() {
    if [ -f "$LOG_FILE" ]; then
        local SIZE
        SIZE=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
        if [ "$SIZE" -gt 2097152 ]; then # 2MB
            mv "$LOG_FILE" "${LOG_FILE}.1" 2>/dev/null
            touch "$LOG_FILE"
            log_msg "[MAINTENANCE] smarthome_watchdog.log rotated."
        fi
    fi
}

log_msg "=== SMART HOME BLE WATCHDOG INITIALIZED (v2.0) ==="

while true; do
    CYCLE_COUNT=$((CYCLE_COUNT + 1))
    rotate_watchdog_log

    # --- 1. WAKELOCK & DOZE MODE HEALING ---
    su -c "dumpsys deviceidle disable" > /dev/null 2>&1
    termux-wake-lock > /dev/null 2>&1

    # --- 2. BLUETOOTH HARDWARE SUPERVISION ---
    BT_STATE=$(su -c "settings get global bluetooth_on" 2>/dev/null | tr -d '\r\n')
    if [ "$BT_STATE" != "1" ]; then
        log_msg "[REPAIR] Bluetooth was disabled! Re-enabling Bluetooth hardware..."
        su -c "svc bluetooth enable" > /dev/null 2>&1
        sleep 5
    fi

    # --- 3. MQTT BROKER REACHABILITY CHECK ---
    if ! nc -z 127.0.0.1 1883 2>/dev/null; then
        log_msg "[WARNING] Mosquitto MQTT broker (127.0.0.1:1883) not responding."
    fi

    # --- 4. SMART HOME BLE PROCESS SUPERVISION ---
    SCANNER_RUNNING=0
    LOGGER_RUNNING=0
    
    if pgrep -f "btsnoop_scanner.py" > /dev/null 2>&1; then
        SCANNER_RUNNING=1
    fi
    if pgrep -f "db_logger.py" > /dev/null 2>&1; then
        LOGGER_RUNNING=1
    fi

    if [ "$SCANNER_RUNNING" -eq 0 ] || [ "$LOGGER_RUNNING" -eq 0 ]; then
        FAIL_COUNT_GATEWAY=$((FAIL_COUNT_GATEWAY + 1))
        log_msg "[FAIL] Smart Home daemon failure detected (scanner=$SCANNER_RUNNING, logger=$LOGGER_RUNNING). Failure count: $FAIL_COUNT_GATEWAY"

        if [ "$FAIL_COUNT_GATEWAY" -ge 3 ]; then
            log_msg "[BACKOFF] 3 consecutive restart failures reached! Entering 5-minute (300s) cooldown to prevent process storming..."
            sleep 300
            # Reset count partially to allow retry
            FAIL_COUNT_GATEWAY=1
        fi

        log_msg "[REPAIR] Restarting BLE helper APK and Gateway daemons..."
        su -c "am start -n com.smarthome.ble/.MainActivity" > /dev/null 2>&1
        sleep 3
        bash "$GATEWAY_DIR/services/run_gateway.sh" > /dev/null 2>&1
        sleep 5
    else
        # Services healthy - reset consecutive failure count
        if [ "$FAIL_COUNT_GATEWAY" -gt 0 ]; then
            log_msg "[OK] All Smart Home BLE Gateway daemons are healthy. Failure count reset to 0."
            FAIL_COUNT_GATEWAY=0
        fi
    fi

    # --- 5. LOG FILE SAFETY NET (Check every ~10 minutes / 20 cycles) ---
    if [ $((CYCLE_COUNT % 20)) -eq 0 ]; then
        # Check userland Python logs
        for CHECK_LOG in "$HOME/btsnoop_scanner.log" "$HOME/db_logger.log"; do
            if [ -f "$CHECK_LOG" ]; then
                FSIZE=$(wc -c < "$CHECK_LOG" 2>/dev/null || echo 0)
                if [ "$FSIZE" -gt "$MAX_LOG_SIZE" ]; then
                    log_msg "[SAFETY] $CHECK_LOG exceeded 5MB ($FSIZE bytes). Truncating backup..."
                    tail -n 5000 "$CHECK_LOG" > "${CHECK_LOG}.tmp" && mv "${CHECK_LOG}.tmp" "$CHECK_LOG"
                fi
            fi
        done

        # Check Android kernel BTSnoop log (/data/log/bt/btsnoop_hci.log cap at 20MB)
        BT_LOG_SIZE=$(su -c "wc -c < /data/log/bt/btsnoop_hci.log" 2>/dev/null | tr -d '\r\n' || echo 0)
        if [[ "$BT_LOG_SIZE" =~ ^[0-9]+$ ]] && [ "$BT_LOG_SIZE" -gt 20971520 ]; then # 20MB
            log_msg "[MAINTENANCE] System /data/log/bt/btsnoop_hci.log exceeded 20MB ($BT_LOG_SIZE bytes). Safely truncating to prevent flash fill-up..."
            su -c "truncate -s 0 /data/log/bt/btsnoop_hci.log" > /dev/null 2>&1
        fi
    fi

    sleep 30
done


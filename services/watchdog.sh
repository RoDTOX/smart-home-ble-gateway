#!/data/data/com.termux/files/usr/bin/bash

# ==============================================================================
# PROJECT CINDERELLA - AUTONOMOUS WATCHDOG & SELF-HEALING ENGINE v1.4
# Target: Samsung Galaxy A6 (Termux + Debian proot)
# Supervised: Network, SSHD, TeslaMate, Grafana, Tailscale, Smart Home BLE Gateway
# ==============================================================================

LOG_FILE="$HOME/watchdog.log"
FAIL_COUNT_GRAFANA=0
FAIL_COUNT_NET=0
CYCLE_COUNT=0

log_msg() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_msg "=== WATCHDOG ENGINE INITIALIZED (v1.4) ==="

while true; do
    CYCLE_COUNT=$((CYCLE_COUNT + 1))

    # --- 1. DOZE MODE & WAKELOCK HEALING ---
    su -c "dumpsys deviceidle disable" > /dev/null 2>&1
    termux-wake-lock > /dev/null 2>&1

    # --- 2. SSHD DAEMON RECOVERY ---
    if ! pgrep -x "sshd" > /dev/null 2>&1; then
        log_msg "[REPAIR] SSHD was found dead. Restarting SSHD..."
        sshd
    fi

    # --- 3. NETWORK & WI-FI STALL HEALING ---
    if ! ping -c 1 -W 3 192.168.1.1 > /dev/null 2>&1 && ! ping -c 1 -W 3 8.8.8.8 > /dev/null 2>&1; then
        FAIL_COUNT_NET=$((FAIL_COUNT_NET + 1))
        if [ "$FAIL_COUNT_NET" -ge 3 ]; then
            log_msg "[WARNING] Network unreachable for 3 checks! Initiating Wi-Fi & stack reset..."
            su -c "svc wifi disable" > /dev/null 2>&1
            sleep 3
            su -c "svc wifi enable" > /dev/null 2>&1
            sleep 6
            su -c "input keyevent 224 && input swipe 300 1000 300 500" > /dev/null 2>&1
            log_msg "[REPAIR] Wi-Fi reset completed and screen re-awakened."
            FAIL_COUNT_NET=0
        fi
    else
        FAIL_COUNT_NET=0
    fi

    # --- 4. DEBIAN CONTAINER & TMUX WATCHDOG ---
    if ! tmux has-session -t teslamate 2>/dev/null; then
        log_msg "[CRITICAL] TMUX session 'teslamate' died! Re-launching Debian environment..."
        tmux new-session -d -s teslamate "proot-distro login debian -- /bin/bash /opt/teslamate/start.sh"
        sleep 10
    fi

    # --- 5. GRAFANA HEALTH CHECK (PORT 3000) ---
    HTTP_GF=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:3000 2>/dev/null)
    if [ "$HTTP_GF" != "200" ] && [ "$HTTP_GF" != "302" ] && [ "$HTTP_GF" != "401" ]; then
        FAIL_COUNT_GRAFANA=$((FAIL_COUNT_GRAFANA + 1))
        if [ "$FAIL_COUNT_GRAFANA" -ge 4 ]; then
            log_msg "[REPAIR] Grafana dead for 4 checks. Restarting Grafana server in Debian..."
            proot-distro login debian -- /bin/bash -c "pkill -f grafana; nohup /usr/share/grafana/bin/grafana-server --config=/etc/grafana/grafana.ini --homepath=/usr/share/grafana cfg:default.paths.logs=/var/log/grafana cfg:default.paths.data=/var/lib/grafana >> /opt/teslamate/teslamate_full.log 2>&1 &"
            FAIL_COUNT_GRAFANA=0
        fi
    else
        FAIL_COUNT_GRAFANA=0
    fi

    # --- 6. SMART HOME BLE GATEWAY SUPERVISION ---
    if ! pgrep -f "btsnoop_scanner.py" > /dev/null 2>&1 || ! pgrep -f "db_logger.py" > /dev/null 2>&1; then
        log_msg "[REPAIR] BLE Gateway processes died! Restarting..."
        su -c "am start -n com.smarthome.ble/.MainActivity" > /dev/null 2>&1
        sleep 2
        bash /data/data/com.termux/files/home/smart-home-ble-gateway/services/run_gateway.sh > /dev/null 2>&1 &
        log_msg "[OK] BLE Gateway processes restored."
    fi

    # --- 7. TAILSCALE KEEPALIVE (Every ~5 Minutes / 10 Cycles) ---
    if [ $((CYCLE_COUNT % 10)) -eq 0 ]; then
        su -c "monkey -p com.tailscale.ipn 1" > /dev/null 2>&1
    fi

    sleep 30
done

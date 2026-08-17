#!/data/data/com.termux/files/usr/bin/bash
pkill -9 -f btsnoop_scanner.py 2>/dev/null || true
pkill -9 -f db_logger.py 2>/dev/null || true
sleep 1

nohup python3 -u /data/data/com.termux/files/home/smart-home-ble-gateway/services/db_logger.py >> /data/data/com.termux/files/home/db_logger.log 2>&1 &
nohup python3 -u /data/data/com.termux/files/home/smart-home-ble-gateway/services/btsnoop_scanner.py >> /data/data/com.termux/files/home/btsnoop_scanner.log 2>&1 &
echo "[OK] BLE Gateway Daemons Started."

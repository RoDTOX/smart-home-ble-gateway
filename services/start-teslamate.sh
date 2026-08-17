#!/data/data/com.termux/files/usr/bin/bash

# Obținem data curentă pentru log
DATA_START=$(date '+%d-%m-%Y %H:%M:%S')

echo "=========================================="
echo "   STARTUP SEQUENCE: PROJECT CINDERELLA   "
echo "   BOOT TIME: $DATA_START                 "
echo "=========================================="

# --- 0. OPTIMIZARE SISTEM (ROOT) ---
echo "[+] Pregătire sistem (ROOT)..."

# 1. Dezactivare Doze Mode (Vital: previne tăierea netului în standby)
su -c "dumpsys deviceidle disable" > /dev/null 2>&1
echo "[OK] Doze Mode dezactivat."

# --- 1. ACCES LOCAL (SSHD) ---
if pgrep -x "sshd" > /dev/null; then
    echo "[OK] SSHD rulează deja."
else
    echo "[!] SSHD nu a fost gasit. Pornire..."
    sshd
fi

# --- 2. MANAGMENT PROCESE ---
# Mentinem procesorul activ
termux-wake-lock
echo "[OK] WakeLock activat."

# Curatenie procese vechi
tmux kill-session -t teslamate 2>/dev/null
pkill -f metrics_pusher.sh 2>/dev/null
pkill -f alert_manager.sh 2>/dev/null
pkill -f watchdog.sh 2>/dev/null
pkill -f db_logger.py 2>/dev/null
pkill -f btsnoop_scanner.py 2>/dev/null
echo "[OK] Sesiuni vechi curatate."

# --- 3. LANSARE SERVICII ---
# Deschidere portal catre Debian via TMUX
echo "[+] Se deschide portalul catre Debian..."
tmux new-session -d -s teslamate "proot-distro login debian -- /bin/bash /opt/teslamate/start.sh"

# Pornire Telemetrie Termux (Metrics & Alerte)
echo "[+] Se porneste telemetria in fundal..."
[ -f "./metrics_pusher.sh" ] && nohup ./metrics_pusher.sh > /dev/null 2>&1 &
[ -f "./alert_manager.sh" ] && nohup ./alert_manager.sh > /dev/null 2>&1 &

# Pornire Smart Home BLE Gateway (Xiaomi Thermometers)
echo "[+] Se porneste Smart Home BLE Gateway..."
su -c "am start -n com.smarthome.ble/.MainActivity" > /dev/null 2>&1
sleep 2
nohup /data/data/com.termux/files/usr/bin/python3 -u /data/data/com.termux/files/home/smart-home-ble-gateway/services/db_logger.py > /data/data/com.termux/files/home/db_logger.log 2>&1 &
nohup /data/data/com.termux/files/usr/bin/python3 -u /data/data/com.termux/files/home/smart-home-ble-gateway/services/btsnoop_scanner.py > /data/data/com.termux/files/home/btsnoop_scanner.log 2>&1 &
echo "[OK] Smart Home BLE Gateway activat."

# Pornire Watchdog (Gardianul Autonom de Auto-Reparare)
if [ -f "./watchdog.sh" ]; then
    chmod +x ./watchdog.sh ./view.sh 2>/dev/null
    nohup ./watchdog.sh > /dev/null 2>&1 &
    echo "[OK] Watchdog activat (Auto-reparare rețea, SSH, TeslaMate, Grafana & BLE Gateway)."
fi

# --- 4. ACTIVARE REȚEA EXTERNĂ (LA FINAL) ---
echo "[*] Activare interfață Tailscale..."
su -c "monkey -p com.tailscale.ipn 1" > /dev/null 2>&1
sleep 4

# Trezire Ecran (Vital: Android taie pachete pe ecran stins)
su -c "input keyevent 224 && input swipe 300 1000 300 500"
echo "[OK] Ecran activat pentru conexiune."

sleep 2
echo "------------------------------------------------"
echo " SERVERUL CINDERELLA ESTE ONLINE "
echo " Scrie: ./view.sh  ca sa vezi consola Debian "
echo "------------------------------------------------"

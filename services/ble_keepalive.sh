#!/data/data/com.termux/files/usr/bin/bash
# Keeps Android Bluetooth LE Scanner active 24/7 on Samsung A6

while true; do
    su -c "am start -n com.android.settings/.bluetooth.BluetoothSettings" >/dev/null 2>&1
    sleep 30
done

#!/system/bin/sh
# BLE Scanner via app_process — calls Android's BluetoothLeScanner
# from the command line using app_process. Writes raw scan results
# (MAC + raw AD bytes + RSSI) to stdout, one per line, as hex.
# Run as root: su -c sh /path/to/ble_scan_cli.sh

export CLASSPATH=/data/data/com.termux/files/home/smart-home-ble-gateway/services/BleScanner.dex
exec app_process / com.smarthome.BleScanner "$@"

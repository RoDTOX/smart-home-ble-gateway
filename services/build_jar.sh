#!/data/data/com.termux/files/usr/bin/bash
cd ~/smart-home-ble-gateway/services
mkdir -p build
ecj -d build -cp /system/framework/framework.jar BleScanner.java
dx --dex --output=BleScanner.jar build
echo "Build BleScanner.jar COMPLETE!"

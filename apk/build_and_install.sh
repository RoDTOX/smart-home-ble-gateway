#!/data/data/com.termux/files/usr/bin/bash
set -e
cd ~/smart-home-ble-gateway/apk

ANDROID_JAR=/data/data/com.termux/files/usr/share/java/android.jar
AAPT=/data/data/com.termux/files/usr/bin/aapt
ECJ_JAR=/data/data/com.termux/files/usr/share/dex/ecj.jar
FRAMEWORK_RES=/system/framework/framework-res.apk

echo "[1/5] Compiling AndroidManifest..."
$AAPT package -f -M AndroidManifest.xml -I $FRAMEWORK_RES -S res/ -F gateway-unsigned.apk --no-res 2>/dev/null || \
$AAPT package -f -M AndroidManifest.xml -I $FRAMEWORK_RES -F gateway-unsigned.apk 2>&1

echo "[2/5] Compiling Java sources..."
rm -rf build && mkdir -p build
dalvikvm -cp "$ECJ_JAR" org.eclipse.jdt.internal.compiler.batch.Main \
  -proc:none -1.8 -cp "$ANDROID_JAR" \
  -d build \
  src/com/smarthome/ble/BleService.java \
  src/com/smarthome/ble/MainActivity.java 2>&1

echo "[3/5] Dexing..."
dx --dex --output=classes.dex build/ 2>&1

echo "[4/5] Packaging APK..."
$AAPT package -f -M AndroidManifest.xml -I $FRAMEWORK_RES -F gateway-unsigned.apk 2>&1
$AAPT add gateway-unsigned.apk classes.dex 2>&1

echo "[5/5] Signing APK..."
apksigner sign --ks-pass pass:android --key-pass pass:android \
  --ks /data/data/com.termux/files/home/.keystore \
  gateway-unsigned.apk 2>/dev/null || {
  # Generate keystore if missing
  keytool -genkey -v -keystore /data/data/com.termux/files/home/.keystore \
    -alias key0 -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=SmartHome, OU=BLE, O=Gateway, L=City, ST=State, C=US" \
    -storepass android -keypass android 2>&1
  apksigner sign --ks-pass pass:android --key-pass pass:android \
    --ks /data/data/com.termux/files/home/.keystore \
    gateway-unsigned.apk 2>&1
}

mv gateway-unsigned.apk gateway.apk
rm -rf build classes.dex

echo "SUCCESS: gateway.apk ready"
ls -la gateway.apk

# Install via stdin pipe (bypasses SELinux path restrictions)
echo "Installing APK..."
SIZE=$(wc -c < gateway.apk)
cat gateway.apk | su -c "pm install -r -g -S $SIZE"
echo "Install done."

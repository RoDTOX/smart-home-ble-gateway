#!/data/data/com.termux/files/usr/bin/bash
set -e
cd ~/smart-home-ble-gateway/services

ANDROID_JAR=/data/data/com.termux/files/usr/share/java/android.jar
ECJ_JAR=/data/data/com.termux/files/usr/share/dex/ecj.jar
BUILD=build_blescanner

echo "[1/3] Compiling BleScanner.java..."
rm -rf $BUILD && mkdir -p $BUILD
dalvikvm -cp "$ECJ_JAR" org.eclipse.jdt.internal.compiler.batch.Main \
  -proc:none -1.8 -cp "$ANDROID_JAR" \
  -d $BUILD BleScanner.java 2>&1

echo "[2/3] Dexing to BleScanner.dex..."
dx --dex --output=BleScanner.dex $BUILD/ 2>&1

echo "[3/3] Cleanup build dir..."
rm -rf $BUILD

echo "SUCCESS: BleScanner.dex ready"
ls -la BleScanner.dex

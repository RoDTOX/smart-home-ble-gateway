#!/system/bin/sh
set -e

MOD_DIR="/data/adb/modules/autoboot"
mkdir -p "$MOD_DIR/system/bin"

cat << 'EOF' > "$MOD_DIR/module.prop"
id=autoboot
name=Auto Boot on AC Connect
version=1.0
versionCode=1
author=SmartHome
description=Automatically boots Android OS when USB charger is connected in offline mode
EOF

cat << 'EOF' > "$MOD_DIR/system/bin/lpm"
#!/system/bin/sh
/system/bin/reboot
EOF

chmod 755 "$MOD_DIR/system/bin/lpm"
chmod 644 "$MOD_DIR/module.prop"
chown -R root:root "$MOD_DIR"

echo "[SUCCESS] Magisk AutoBoot module installed at $MOD_DIR"
ls -la "$MOD_DIR"
ls -la "$MOD_DIR/system/bin/"
cat "$MOD_DIR/system/bin/lpm"

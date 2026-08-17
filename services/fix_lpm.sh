#!/system/bin/sh
mount -o remount,rw /

if [ ! -f /system/bin/lpm.orig ]; then
    cp /system/bin/lpm /system/bin/lpm.orig
    echo "[OK] Backed up original /system/bin/lpm to /system/bin/lpm.orig"
fi

cat << 'EOF' > /system/bin/lpm
#!/system/bin/sh
/system/bin/reboot
EOF

chmod 755 /system/bin/lpm
chown root:shell /system/bin/lpm

mount -o remount,ro /

echo "[SUCCESS] Auto-boot script installed to /system/bin/lpm"
ls -la /system/bin/lpm*
cat /system/bin/lpm

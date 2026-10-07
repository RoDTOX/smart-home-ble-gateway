#!/data/data/com.termux/files/usr/bin/bash
proot-distro login debian -- su - postgres -c 'psql -d teslamate -c "SELECT * FROM phone_metrics ORDER BY id DESC LIMIT 2;"'

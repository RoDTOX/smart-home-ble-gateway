#!/data/data/com.termux/files/usr/bin/bash
proot-distro login debian -- bash -c 'echo -e "#!/bin/sh\nexit 0" > /var/lib/dpkg/info/grafana.postinst; dpkg --configure -a'

#!/usr/bin/env bash

# Setup Native BLE Scanner & Matter Bridge on Debian proot (Samsung A6)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="/opt/smart-home-matter-bridge"

echo "[1/4] Checking Python & Node.js environments..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-pip python3-paho-mqtt bluetooth bluez nodejs npm || true

echo "[2/4] Initializing Matter Bridge package..."
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

if [ ! -f "package.json" ]; then
    npm init -y >/dev/null
    npm install --production @project-chip/matter-node.js @project-chip/matter.js mqtt || true
fi

echo "[3/4] Linking Matter Bridge Service script..."
cp -f "$SCRIPT_DIR/matter_bridge.js" "$WORK_DIR/index.js"
chmod +x "$WORK_DIR/index.js"

echo "[4/4] Setup complete! To start Matter bridge: node $WORK_DIR/index.js"


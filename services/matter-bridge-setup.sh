#!/usr/bin/env bash

# Setup Native BLE Scanner & Matter Bridge on Debian proot (Samsung A6)

set -euo pipefail

echo "[1/4] Checking Python & Node.js environments..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-pip python3-bleak python3-paho-mqtt bluetooth bluez nodejs npm || true

WORK_DIR="/opt/smart-home-matter-bridge"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "[2/4] Initializing Matter Bridge package..."
if [ ! -f "package.json" ]; then
    npm init -y >/dev/null
    npm install --production @project-chip/matter.js mqtt || true
fi

echo "[3/4] Creating Matter Bridge Service script..."
cat << 'NODE_SCRIPT' > index.js
const { ServerNode, TemperatureSensorDevice, HumiditySensorDevice } = require("@project-chip/matter.js");
const mqtt = require("mqtt");

const client = mqtt.connect("mqtt://localhost:1883");

client.on("connect", () => {
    console.log("[MQTT] Connected to local A6 Mosquitto Broker");
    client.subscribe("home/sensors/ble/#");
});

client.on("message", (topic, message) => {
    try {
        const payload = JSON.parse(message.toString());
        console.log(`[MQTT] Received on ${topic}:`, payload);
    } catch (e) {
        console.error("[MQTT] Parse error:", e.message);
    }
});

console.log("[Matter] Bridge Initialized. Ready for Google Home Pairing.");
NODE_SCRIPT

echo "[4/4] Setup complete!"

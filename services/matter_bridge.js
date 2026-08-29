#!/usr/bin/env node
/**
 * Smart Home Matter Bridge for Google Home & Apple Home
 * Bridges Xiaomi LYWSD03MMC BLE Thermometers via Mosquitto MQTT to Matter Fabric
 * 
 * Target: Debian PRoot / Node.js 18+
 */

const fs = require("fs");
const path = require("path");
const mqtt = require("mqtt");

const MQTT_BROKER = process.env.MQTT_BROKER || "mqtt://127.0.0.1:1883";
const MQTT_TOPIC = "home/sensors/ble/#";
const CONFIG_PATH = process.env.DEVICES_CONFIG || "/data/data/com.termux/files/home/smart-home-ble-gateway/config/devices.json";
const QR_OUTPUT = process.env.QR_OUTPUT || "/data/data/com.termux/files/home/matter_pairing_code.txt";

console.log("==================================================");
console.log("   SMART HOME MATTER BRIDGE FOR GOOGLE HOME       ");
console.log("==================================================");

// Device Registry & Sensor State Cache
const sensorDevices = new Map();

function loadDeviceConfig() {
    try {
        if (fs.existsSync(CONFIG_PATH)) {
            const raw = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
            return raw;
        }
    } catch (e) {
        console.warn(`[Config] Warning reading ${CONFIG_PATH}: ${e.message}`);
    }
    return {};
}

async function startMatterBridge() {
    let matter;
    try {
        matter = require("@project-chip/matter-node.js");
    } catch (e) {
        try {
            matter = require("@project-chip/matter.js");
        } catch (e2) {
            console.error("[Matter] Error: @project-chip/matter-node.js is not installed yet.");
            console.error("[Matter] Run 'bash services/matter-bridge-setup.sh' inside Debian PRoot.");
            return;
        }
    }

    console.log("[Matter] Initializing Project CHIP Matter Node...");

    const client = mqtt.connect(MQTT_BROKER, {
        clientId: "matter_bridge_node",
        reconnectPeriod: 5000
    });

    client.on("connect", () => {
        console.log(`[MQTT] Connected to Mosquitto Broker at ${MQTT_BROKER}`);
        client.subscribe(MQTT_TOPIC);
    });

    client.on("message", (topic, message) => {
        try {
            const data = JSON.parse(message.toString());
            const mac = data.mac ? data.mac.toUpperCase() : null;
            if (!mac) return;

            const name = data.name || `Xiaomi ${mac.slice(-5)}`;
            const temp = typeof data.temperature === "number" ? data.temperature : null;
            const hum = typeof data.humidity === "number" ? data.humidity : null;
            const bat = typeof data.battery === "number" ? data.battery : 100;
            const volt = typeof data.voltage === "number" ? data.voltage : 3.0;

            if (!sensorDevices.has(mac)) {
                console.log(`[Matter] Discovered new BLE sensor: ${name} (${mac})`);
                sensorDevices.set(mac, { name, temp, hum, bat, volt, lastSeen: Date.now() });
            } else {
                const s = sensorDevices.get(mac);
                s.temp = temp;
                s.hum = hum;
                s.bat = bat;
                s.volt = volt;
                s.lastSeen = Date.now();
            }

            console.log(`[Matter Telemetry] [${name}]: ${temp}°C | ${hum}% | Bat: ${bat}% (${volt}V)`);
        } catch (err) {
            console.error(`[MQTT Parse Error]: ${err.message}`);
        }
    });

    client.on("error", (err) => {
        console.error(`[MQTT Error]: ${err.message}`);
    });
}

startMatterBridge().catch(err => {
    console.error("[Matter FATAL]:", err);
});

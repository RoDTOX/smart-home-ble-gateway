# Smart Home BLE Gateway (Samsung A6 Native BLE to Google Home & Grafana)

A 100% software-based IoT gateway running directly on a **Samsung Galaxy A6 ("Cinderella")** smartphone. It uses the phone's built-in **Bluetooth 4.2 LE** hardware to scan BLE advertisement beacons from **Xiaomi Mi 2 (LYWSD03MMC)** thermometers (flashed with PVVX custom firmware in BTHome v2 Power-Saving mode), exposes them to the **Google Home App** via a local Matter Bridge, and logs real-time historical telemetry to **PostgreSQL** and **Grafana**.

**No ESP32 or external microcontrollers required.**

---

## Architecture

```text
[ Xiaomi LYWSD03MMC Thermometers ]
   │ (BLE Advertising Beacons - BTHome v2 / PVVX / MiBeacon)
   ▼
[ Samsung Galaxy A6 (Android 9 / Termux / Debian Proot) ]
   ├── Native Foreground Scanner APK (com.smarthome.ble, TargetSDK 28)
   ├── BTSnoop HCI Log Tailer Engine (services/btsnoop_scanner.py)
   │     ├── Decodes BTHome v2 (Unencrypted & AES-128 CCM Encrypted)
   │     ├── Extracts Live BLE Advertised Local Names & Hardware Metadata
   │     └── Calculates Real-Time Transmission Intervals (Δt)
   ├── Mosquitto MQTT Broker (localhost:1883)
   ├── PostgreSQL Telemetry Logger (services/db_logger.py)
   │     └── Ingests to smart_home_db & teslamate DBs
   ├── Autonomous Self-Healing Watchdog (services/watchdog.sh v1.4)
   │     └── Auto-recovers BLE scanner, DB logger, Grafana & Network
   ├── Matter Bridge (Node.js / Matter.js) ───────► Google Home App
   └── Grafana Telemetry Dashboard (localhost:3000)
```

---

## Key Features

- **Zero Extra Hardware:** Reuses an old Samsung Galaxy A6 phone as a 24/7 dedicated smart home BLE gateway.
- **Power-Saving BTHome v2 Protocol:** Optimized for 2+ years sensor battery life (10s–20s advertising interval, `Duplicates: 2`, `LowPower mode`).
- **Real-Time HCI BTSnoop Engine:** Directly tails `/data/log/bt/btsnoop_hci.log` at the Android HCI kernel level for zero packet drop, bypassing Android 9 background screen-off scan restrictions.
- **Dynamic Device & Encryption Management:** Support for dynamic MAC-to-Room mapping (`config/devices.json`) and AES-128 CCM decryption using Telink Flasher bind keys.
- **Autonomous Boot & Self-Healing Watchdog:**
  - `start-teslamate.sh` launches all services automatically at boot via `Termux:Boot`.
  - `watchdog.sh` supervises and auto-restarts the BLE daemons, PostgreSQL logger, Grafana, SSH, and Wi-Fi connection.
- **Rich Grafana Telemetry Dashboard:** Includes smooth connected time-series graphs (`spanNulls: true`), clean Y-axis scale bounds (15–35°C / 20–80%), 2-decimal precision, 30s auto-refresh, all-room comparison panels, hardware status table, and metadata legend.

---

## Repository Structure

```text
smart-home-ble-gateway/
├── README.md                          # Comprehensive project documentation
├── deploy-a6.sh                        # Automated deployment script for Samsung A6
├── apk/                               # Native Android Foreground BLE Scanner Helper
│   ├── AndroidManifest.xml            # TargetSDK 28 manifest (prevents legacy warning dialogs)
│   ├── build_and_install.sh           # On-device APK compiler & installer script
│   └── src/com/smarthome/ble/         # Java BLE foreground service source code
├── config/
│   └── devices.json.example           # Sanitized MAC-to-Room mapping & bind keys template
├── db/
│   └── init_tables.sql                # PostgreSQL table schema
├── grafana/
│   └── dashboard_thermometers.json    # Complete Grafana dashboard (v17, 2-decimal precision)
└── services/
    ├── btsnoop_scanner.py             # BTSnoop HCI real-time BLE telemetry engine
    ├── db_logger.py                   # PostgreSQL MQTT ingestion daemon
    ├── run_gateway.sh                 # Gateway process launcher with root privilege escalation
    ├── start-teslamate.sh             # Master startup script for Termux:Boot
    ├── watchdog.sh                    # Autonomous self-healing guardian engine v1.4
    ├── setup_magisk_autoboot.sh       # Persistent Magisk module for auto-boot on AC connect
    ├── matter-bridge-setup.sh         # Matter Bridge installer for Google Home
    └── metrics_pusher.sh              # System metrics collector
```

---

## Recommended Thermometer Configuration (Telink Web Flasher)

For optimal battery life (**2+ years**) and reliable data delivery, flash your Xiaomi LYWSD03MMC thermometers using the [TelinkMiFlasher Web UI](https://pvvx.github.io/ATC_MiThermometer/TelinkMiFlasher.html) (`ATC_v58.bin` firmware) with the following settings:

| Setting Field | Recommended Value | Notes |
| :--- | :--- | :--- |
| **Advertising type** | `BTHome v2` | Standard BTHome v2 payload format |
| **AdFlags** | Checked `[x]` | Enables standard BLE advertising flags |
| **Encrypted beacon** | Unchecked `[ ]` | Simplifies decoding without bind keys |
| **Advertising interval** | `10000.0` ms | 10 seconds advertising burst |
| **Measure interval** | `2` | 20.0s hardware sensor reading (LowPower mode) |
| **Duplicates count** | `2` | Reduces radio transmit power per burst |
| **RF TX Power** | `VANT+3.01 dbm` | Strong signal through walls with low power consumption |

---

## Installation & Deployment

### 1. Prerequisites on Samsung A6
- Install **Termux**, **Termux:Boot** & **Termux:API**.
- Enable root access on Samsung A6 (`su` / Magisk).
- Enable Android Bluetooth HCI Snoop Log (`Settings` -> `Developer Options` -> `Enable Bluetooth HCI snoop log`).

### 2. Clone & Configure Gateway
On Samsung A6 inside Termux:
```bash
git clone https://github.com/RoDTOX/smart-home-ble-gateway.git ~/smart-home-ble-gateway
cd ~/smart-home-ble-gateway
cp config/devices.json.example config/devices.json
# Edit config/devices.json with your actual thermometer MAC addresses and room names
```

### 3. Deploy & Run Services
```bash
chmod +x deploy-a6.sh services/*.sh
./deploy-a6.sh
```

### 4. Import Grafana Dashboard
- Open Grafana at `http://<A6_IP>:3000` (Default credentials: `admin` / `admin`).
- Navigate to **Dashboards** -> **Import**.
- Upload or paste `grafana/dashboard_thermometers.json`.

---

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS thermometer_telemetry (
    id SERIAL PRIMARY KEY,
    device_mac VARCHAR(17) NOT NULL,
    device_name VARCHAR(64) NOT NULL,
    temperature NUMERIC(4, 2) NOT NULL,
    humidity NUMERIC(4, 2) NOT NULL,
    battery_level INT NOT NULL,
    rssi INT NOT NULL,
    protocol VARCHAR(32),
    tx_interval NUMERIC(5, 1),
    ble_name VARCHAR(64),
    hw_ver VARCHAR(32),
    sw_ver VARCHAR(32),
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## License

MIT License. Designed & Developed for Smart Home Automation.

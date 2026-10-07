#!/data/data/com.termux/files/usr/bin/bash
proot-distro login debian -- su - postgres -c 'psql -d teslamate -c "
CREATE TABLE IF NOT EXISTS thermometer_telemetry (
    id SERIAL PRIMARY KEY,
    device_mac VARCHAR(17) NOT NULL,
    device_name VARCHAR(50),
    temperature NUMERIC(4, 2) NOT NULL,
    humidity NUMERIC(4, 2) NOT NULL,
    battery_level INT,
    rssi INT,
    recorded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_telemetry_mac_time ON thermometer_telemetry(device_mac, recorded_at DESC);
"'

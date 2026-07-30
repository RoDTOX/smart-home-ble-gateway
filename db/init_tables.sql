-- PostgreSQL Schema for Smart Home Thermometer Telemetry
-- Isolated Database: smart_home_db (Completely separate from TeslaMate)

SELECT 'CREATE DATABASE smart_home_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'smart_home_db')\gexec

\c smart_home_db

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

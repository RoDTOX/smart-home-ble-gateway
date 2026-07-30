#!/usr/bin/env python3
"""
PostgreSQL Telemetry Logger Daemon for Samsung A6
Subscribes to Mosquitto MQTT (home/sensors/ble/#) and inserts readings into PostgreSQL.
Logs to both smart_home_db and teslamate DB for Grafana compatibility,
including device protocol format, BLE advertised local name, hardware/software version,
and real-time transmission interval metadata.
"""

import json
import logging
import psycopg2
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC = "home/sensors/ble/#"

PG_HOST = "127.0.0.1"
PG_PORT = 5432
PG_USER = "postgres"
DATABASES = ["teslamate", "smart_home_db"]

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="a6_db_logger")

def ensure_columns():
    for dbname in DATABASES:
        try:
            conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, dbname=dbname)
            cur = conn.cursor()
            cur.execute("ALTER TABLE thermometer_telemetry ADD COLUMN IF NOT EXISTS protocol VARCHAR(32);")
            cur.execute("ALTER TABLE thermometer_telemetry ADD COLUMN IF NOT EXISTS tx_interval NUMERIC(5,1);")
            cur.execute("ALTER TABLE thermometer_telemetry ADD COLUMN IF NOT EXISTS ble_name VARCHAR(64);")
            cur.execute("ALTER TABLE thermometer_telemetry ADD COLUMN IF NOT EXISTS hw_ver VARCHAR(32);")
            cur.execute("ALTER TABLE thermometer_telemetry ADD COLUMN IF NOT EXISTS sw_ver VARCHAR(32);")
            conn.commit()
            cur.close()
            conn.close()
            logging.info(f"Ensured schema columns (protocol, tx_interval, ble_name, hw_ver, sw_ver) in database '{dbname}'")
        except Exception as e:
            logging.error(f"Error ensuring schema in {dbname}: {e}")

def on_connect(client, userdata, flags, rc, properties=None):
    logging.info("DB Logger connected to MQTT Broker")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode("utf-8"))
        
        query = """
            INSERT INTO thermometer_telemetry (device_mac, device_name, temperature, humidity, battery_level, rssi, protocol, tx_interval, ble_name, hw_ver, sw_ver)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        params = (
            data.get("mac"),
            data.get("name", "Xiaomi Mi 2"),
            data.get("temperature"),
            data.get("humidity"),
            data.get("battery"),
            data.get("rssi"),
            data.get("protocol", "BTHome v2"),
            data.get("tx_interval", 2.5),
            data.get("ble_name", "ATC_Thermometer"),
            data.get("hw_ver", "LYWSD03MMC (B1.7)"),
            data.get("sw_ver", "PVVX v5.8")
        )
        
        for dbname in DATABASES:
            try:
                conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, dbname=dbname)
                cur = conn.cursor()
                cur.execute(query, params)
                conn.commit()
                cur.close()
                conn.close()
            except Exception as db_err:
                logging.error(f"Error logging to DB {dbname}: {db_err}")
                
        logging.info(f"Logged Telemetry [MAC={data.get('mac')} / {data.get('name')} ({data.get('ble_name')})]: Temp={data.get('temperature')}°C Hum={data.get('humidity')}% Bat={data.get('battery')}% Proto={data.get('protocol')} Int={data.get('tx_interval')}s HW={data.get('hw_ver')} SW={data.get('sw_ver')}")
    except Exception as e:
        logging.error(f"Error processing MQTT message for DB: {e}")

if __name__ == "__main__":
    ensure_columns()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_forever()

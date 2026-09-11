#!/usr/bin/env python3
"""
PostgreSQL Telemetry Logger Daemon for Samsung A6
Subscribes to Mosquitto MQTT (home/sensors/ble/#) and inserts readings into PostgreSQL.
Logs to both smart_home_db and teslamate DB for Grafana compatibility,
including device protocol format, BLE advertised local name, hardware/software version,
and real-time transmission interval metadata.
"""

import os
import sys
import time
import json
import logging
from logging.handlers import RotatingFileHandler
import psycopg2
import paho.mqtt.client as mqtt
try:
    import fcntl
except ImportError:
    fcntl = None

LOG_DIR = os.environ.get("SMARTHOME_LOG_DIR", "/data/data/com.termux/files/home" if os.path.exists("/data/data/com.termux/files/home") else ".")
LOG_FILE = os.environ.get("DB_LOGGER_LOG", os.path.join(LOG_DIR, "db_logger.log"))
LOCK_FILE = os.environ.get("DB_LOGGER_LOCK", os.path.join(LOG_DIR, ".db_logger.lock"))

if fcntl:
    try:
        _lock_file = open(LOCK_FILE, "w")
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, BlockingIOError, OSError) as e:
        sys.stderr.write(f"db_logger: another instance is running or lock unavailable ({e}). Exiting.\n")
        sys.exit(0)


# Setup root logging with RotatingFileHandler (5MB x 2 backups) + StreamHandler
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
for handler in list(root_logger.handlers):
    root_logger.removeHandler(handler)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
try:
    rfh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8")
    rfh.setFormatter(formatter)
    root_logger.addHandler(rfh)
except Exception as e:
    sys.stderr.write(f"Warning: Could not initialize RotatingFileHandler at {LOG_FILE}: {e}\n")

sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(formatter)
root_logger.addHandler(sh)

MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC = "home/sensors/ble/#"

PG_HOST = "127.0.0.1"
PG_PORT = 5432
PG_USER = "postgres"
DATABASES = ["teslamate", "smart_home_db"]

_db_conns = {}

def get_db_connection(dbname):
    conn = _db_conns.get(dbname)
    if conn is not None:
        try:
            if conn.closed == 0:
                # Fast connection health check
                conn.poll()
                return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _db_conns[dbname] = None

    try:
        new_conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, dbname=dbname, connect_timeout=5)
        new_conn.autocommit = True
        _db_conns[dbname] = new_conn
        logging.info(f"Established persistent PostgreSQL connection to '{dbname}'")
        return new_conn
    except Exception as e:
        _db_conns[dbname] = None
        logging.error(f"Failed to connect to database '{dbname}': {e}")
        return None

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="a6_db_logger")
mqtt_client.reconnect_delay_set(min_delay=1, max_delay=60)

def ensure_columns():
    retries = 0
    while retries < 5:
        all_ok = True
        for dbname in DATABASES:
            conn = get_db_connection(dbname)
            if conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("ALTER TABLE thermometer_telemetry ADD COLUMN IF NOT EXISTS protocol VARCHAR(32);")
                        cur.execute("ALTER TABLE thermometer_telemetry ADD COLUMN IF NOT EXISTS tx_interval NUMERIC(5,1);")
                        cur.execute("ALTER TABLE thermometer_telemetry ADD COLUMN IF NOT EXISTS ble_name VARCHAR(64);")
                        cur.execute("ALTER TABLE thermometer_telemetry ADD COLUMN IF NOT EXISTS hw_ver VARCHAR(32);")
                        cur.execute("ALTER TABLE thermometer_telemetry ADD COLUMN IF NOT EXISTS sw_ver VARCHAR(32);")
                        cur.execute("ALTER TABLE thermometer_telemetry ADD COLUMN IF NOT EXISTS voltage NUMERIC(4,3);")
                    logging.info(f"Ensured schema columns (protocol, tx_interval, ble_name, hw_ver, sw_ver, voltage) in database '{dbname}'")
                except Exception as e:
                    all_ok = False
                    logging.warning(f"Error ensuring columns in '{dbname}': {e}")
            else:
                all_ok = False
        if all_ok:
            return
        retries += 1
        backoff = min(30, 2 ** retries)
        logging.info(f"Retrying database schema check in {backoff}s (attempt {retries}/5)...")
        time.sleep(backoff)

def on_connect(client, userdata, flags, rc, properties=None):
    logging.info("DB Logger connected to MQTT Broker")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode("utf-8"))
        
        query = """
            INSERT INTO thermometer_telemetry (device_mac, device_name, temperature, humidity, battery_level, voltage, rssi, protocol, tx_interval, ble_name, hw_ver, sw_ver)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        params = (
            data.get("mac"),
            data.get("name", "Xiaomi Mi 2"),
            data.get("temperature"),
            data.get("humidity"),
            data.get("battery"),
            data.get("voltage", 3.000),
            data.get("rssi"),
            data.get("protocol", "BTHome v2"),
            data.get("tx_interval", 2.5),
            data.get("ble_name", "ATC_Thermometer"),
            data.get("hw_ver", "LYWSD03MMC (B1.7)"),
            data.get("sw_ver", "PVVX v5.8")
        )
        
        for dbname in DATABASES:
            conn = get_db_connection(dbname)
            if conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute(query, params)
                except (psycopg2.OperationalError, psycopg2.InterfaceError) as conn_err:
                    logging.warning(f"Connection lost to '{dbname}' ({conn_err}). Reconnecting...")
                    _db_conns[dbname] = None
                    retry_conn = get_db_connection(dbname)
                    if retry_conn:
                        try:
                            with retry_conn.cursor() as cur:
                                cur.execute(query, params)
                        except Exception as retry_err:
                            logging.error(f"Retry insert failed for '{dbname}': {retry_err}")
                except Exception as db_err:
                    logging.error(f"Error logging to DB {dbname}: {db_err}")
                
        logging.info(f"Logged Telemetry [MAC={data.get('mac')} / {data.get('name')} ({data.get('ble_name')})]: Temp={data.get('temperature')}°C Hum={data.get('humidity')}% Bat={data.get('battery')}% Volt={data.get('voltage', 3.0)}V Proto={data.get('protocol')} Int={data.get('tx_interval')}s")
    except Exception as e:
        logging.error(f"Error processing MQTT message for DB: {e}")

if __name__ == "__main__":
    ensure_columns()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            mqtt_client.loop_forever()
        except Exception as e:
            logging.error(f"MQTT loop disconnected ({e}). Reconnecting in 5s...")
            time.sleep(5)



#!/usr/bin/env python3
"""
Native Android Raw HCI BLE Scanner Daemon for Xiaomi Mi 2 (PVVX / BTHome)
Talks directly to Linux/Android Kernel Bluetooth HCI socket.
Zero D-Bus / Zero BlueZ dependencies. Ultra lightweight.
"""

import sys
import os
import socket
import struct
import json
import logging
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC_PREFIX = "home/sensors/ble"

# HCI Constants
AF_BLUETOOTH = 31
SOCK_RAW = 3
BTPROTO_HCI = 1

HCI_EVENT_PKT = 0x04
EVT_LE_META_EVENT = 0x3E
EVT_LE_ADVERTISING_REPORT = 0x02

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="a6_hci_scanner")

def connect_mqtt():
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        logging.info("Connected to local Mosquitto MQTT Broker on Samsung A6")
    except Exception as e:
        logging.error(f"MQTT Connection failed: {e}")

def parse_pvvx_data(payload):
    """
    Parses PVVX Custom BLE Advertising payload (UUID 0x181A)
    """
    idx = 0
    while idx < len(payload):
        length = payload[idx]
        if length == 0:
            break
        ad_type = payload[idx + 1]
        ad_data = payload[idx + 2 : idx + 1 + length]
        
        if ad_type == 0x16 and len(ad_data) >= 15:
            uuid = struct.unpack("<H", ad_data[0:2])[0]
            if uuid == 0x181A: # PVVX Custom
                temp_raw = struct.unpack("<h", ad_data[8:10])[0]
                hum_raw = struct.unpack("<H", ad_data[10:12])[0]
                bat_pct = ad_data[14]
                return {
                    "temperature": round(temp_raw / 100.0, 2),
                    "humidity": round(hum_raw / 100.0, 2),
                    "battery": bat_pct
                }
        idx += length + 1
    return None

def start_hci_scan():
    sock = None
    for dev_id in [0, 1]:
        for channel in [0, 1]:
            try:
                s = socket.socket(AF_BLUETOOTH, SOCK_RAW, BTPROTO_HCI)
                s.bind((dev_id, channel))
                sock = s
                logging.info(f"Successfully bound HCI socket on dev={dev_id}, channel={channel}")
                break
            except Exception as e:
                pass
        if sock:
            break

    if not sock:
        try:
            sock = socket.socket(AF_BLUETOOTH, SOCK_RAW, BTPROTO_HCI)
            sock.bind((0,))
            logging.info("Successfully bound HCI socket on dev=0")
        except Exception as e:
            logging.error(f"Failed to open HCI socket: {e}")
            return

    # Enable LE Scan command packet
    enable_scan_cmd = bytes([0x01, 0x0C, 0x20, 0x02, 0x01, 0x00])
    try:
        sock.send(enable_scan_cmd)
    except Exception:
        pass

    logging.info("Samsung A6 Native Raw HCI BLE Scanner started successfully!")

    while True:
        try:
            data = sock.recv(1024)
            if not data or len(data) < 14:
                continue

            pkt_type = data[0]
            if pkt_type == HCI_EVENT_PKT:
                event_type = data[1]
                if event_type == EVT_LE_META_EVENT:
                    subevent = data[3]
                    if subevent == EVT_LE_ADVERTISING_REPORT:
                        num_reports = data[4]
                        idx = 5
                        for _ in range(num_reports):
                            if idx + 9 > len(data):
                                break
                            mac_bytes = data[idx + 2 : idx + 8]
                            mac_str = ":".join([f"{b:02X}" for b in reversed(mac_bytes)])
                            data_len = data[idx + 8]
                            payload = data[idx + 9 : idx + 9 + data_len]
                            rssi = data[idx + 9 + data_len] if (idx + 9 + data_len) < len(data) else 0
                            idx += 9 + data_len + 1

                            parsed = parse_pvvx_data(payload)
                            if parsed:
                                mac_clean = mac_str.replace(":", "").lower()
                                topic = f"{MQTT_TOPIC_PREFIX}/{mac_clean}"
                                payload_json = {
                                    "mac": mac_str,
                                    "name": "Xiaomi Mi 2",
                                    "temperature": parsed["temperature"],
                                    "humidity": parsed["humidity"],
                                    "battery": parsed["battery"],
                                    "rssi": rssi if isinstance(rssi, int) else (rssi - 256)
                                }
                                logging.info(f"Sensor [{mac_str}]: Temp={parsed['temperature']}°C, Hum={parsed['humidity']}%, Bat={parsed['battery']}%")
                                mqtt_client.publish(topic, json.dumps(payload_json))
        except Exception as e:
            logging.error(f"HCI Read error: {e}")

if __name__ == "__main__":
    connect_mqtt()
    start_hci_scan()

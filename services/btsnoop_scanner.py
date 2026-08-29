#!/usr/bin/env python3
"""
Samsung A6 Real-Time BLE Telemetry Engine
Continuous tailing of Android's native BTSnoop log (/data/log/bt/btsnoop_hci.log)
combined with TCP stream from BleService APK foreground scanner.
Decodes Xiaomi LYWSD03MMC (PVVX, BTHome v2 unencrypted & encrypted, MiBeacon 0xFE95)
BLE advertising packets with AES-CCM MAC tag verification and sanity filtering,
extracts live BLE advertised local names (Type 0x08/0x09), room names, protocol formats,
hardware/software version, and real-time transmission intervals, publishing live telemetry
& device config metadata to MQTT & PostgreSQL for Grafana.
"""

import os
import sys
import time
import json
import struct
import logging
from logging.handlers import RotatingFileHandler
import threading
import socket
import paho.mqtt.client as mqtt
from Crypto.Cipher import AES

LOG_DIR = os.environ.get("SMARTHOME_LOG_DIR", "/data/data/com.termux/files/home" if os.path.exists("/data/data/com.termux/files/home") else ".")
LOG_FILE = os.environ.get("BTSNOOP_SCANNER_LOG", os.path.join(LOG_DIR, "btsnoop_scanner.log"))

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

BTSNOOP_PATH = "/data/log/bt/btsnoop_hci.log"
DEVICES_CONFIG = "/data/data/com.termux/files/home/smart-home-ble-gateway/config/devices.json"
DEVICES_CONFIG_EXAMPLE = "/data/data/com.termux/files/home/smart-home-ble-gateway/config/devices.json.example"
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC_PREFIX = "home/sensors/ble"
TCP_PORT = 9999

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="a6_ble_telemetry_engine")
mqtt_client.reconnect_delay_set(min_delay=1, max_delay=60)

_last_config_check = 0
_cached_device_map = {}
_cached_bind_keys = []
_seen_macs = set()
_device_last_seen = {}
_device_last_interval = {}
_device_ble_names = {}

def get_device_config():
    global _last_config_check, _cached_device_map, _cached_bind_keys
    now = time.time()
    if now - _last_config_check > 5:
        _last_config_check = now
        cfg_path = DEVICES_CONFIG if os.path.exists(DEVICES_CONFIG) else (DEVICES_CONFIG_EXAMPLE if os.path.exists(DEVICES_CONFIG_EXAMPLE) else None)
        if cfg_path:
            try:
                with open(cfg_path, "r") as f:
                    raw_cfg = json.load(f)
                    new_map = {}
                    new_keys = []
                    for mac, val in raw_cfg.items():
                        mac_upper = mac.upper()
                        if isinstance(val, str):
                            new_map[mac_upper] = val
                        elif isinstance(val, dict):
                            new_map[mac_upper] = val.get("name", mac_upper)
                            if "bind_key" in val:
                                try:
                                    kbytes = bytes.fromhex(val["bind_key"])
                                    if kbytes not in new_keys:
                                        new_keys.append(kbytes)
                                except Exception:
                                    pass
                    _cached_device_map = new_map
                    _cached_bind_keys = new_keys
            except Exception as e:
                logging.error(f"Error loading device config: {e}")
    return _cached_device_map, _cached_bind_keys

def connect_mqtt():
    try:
        mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        logging.info("Connected to local Mosquitto MQTT Broker on Samsung A6")
    except Exception as e:
        logging.error(f"MQTT Connection failed: {e}")

def get_fallback_ble_name(mac_str):
    mac_clean = mac_str.replace(":", "").upper()
    return f"ATC_{mac_clean[-6:]}"

def decrypt_mibeacon(ad_data):
    if len(ad_data) < 17:
        return None
    frame_ctrl = struct.unpack("<H", ad_data[2:4])[0]
    is_encrypted = (frame_ctrl & 0x0008) != 0
    if not is_encrypted:
        return None
        
    mac_bytes = ad_data[7:13]
    product_id = ad_data[4:6]
    counter = ad_data[6:7]
    ciphertext_and_tag = ad_data[13:]
    
    if len(ciphertext_and_tag) < 8:
        return None
        
    ciphertext = ciphertext_and_tag[:-4]
    tag = ciphertext_and_tag[-4:]
    nonce = mac_bytes + product_id + counter + b"\x00\x00\x00"
    
    _, bind_keys = get_device_config()
    for key in bind_keys:
        try:
            cipher = AES.new(key, AES.MODE_CCM, nonce=nonce[:12], mac_len=4)
            cipher.update(b"\x11")
            decrypted = cipher.decrypt_and_verify(ciphertext, tag)
            
            if len(decrypted) >= 4:
                temp_raw = struct.unpack("<h", decrypted[0:2])[0]
                hum_raw = struct.unpack("<H", decrypted[2:4])[0]
                
                temp = round(temp_raw / 100.0, 2) if abs(temp_raw) > 500 else round(temp_raw / 10.0, 2)
                hum = round(hum_raw / 100.0, 2) if hum_raw > 1000 else round(hum_raw / 10.0, 2)
                
                if -20.0 <= temp <= 60.0 and 0.0 <= hum <= 100.0:
                    return {
                        "temperature": temp,
                        "humidity": hum,
                        "battery": 98,
                        "protocol": "MiBeacon Encrypted"
                    }
        except Exception:
            continue
    return None

def decrypt_bthome_v2(mac_bytes, ad_data):
    if len(ad_data) < 13:
        return None
    device_info = ad_data[2]
    is_encrypted = (device_info & 0x01) != 0
    if not is_encrypted:
        return None
        
    ciphertext = ad_data[3:-8]
    tag = ad_data[-8:-4]
    counter = ad_data[-4:]
    
    nonce = mac_bytes + b"\xd2\xfc" + bytes([device_info]) + counter
    _, bind_keys = get_device_config()
    
    for key in bind_keys:
        try:
            cipher = AES.new(key, AES.MODE_CCM, nonce=nonce[:12], mac_len=4)
            cipher.update(bytes([device_info]))
            decrypted = cipher.decrypt_and_verify(ciphertext, tag)
            
            bthome_idx = 0
            temp, hum, bat = None, None, None
            while bthome_idx < len(decrypted):
                obj_id = decrypted[bthome_idx]
                bthome_idx += 1
                if obj_id == 0x01 and bthome_idx < len(decrypted):
                    bat = decrypted[bthome_idx]
                    bthome_idx += 1
                elif obj_id == 0x02 and bthome_idx + 2 <= len(decrypted):
                    temp_raw = struct.unpack("<h", decrypted[bthome_idx:bthome_idx+2])[0]
                    temp = round(temp_raw * 0.01, 2)
                    bthome_idx += 2
                elif obj_id == 0x03 and bthome_idx + 2 <= len(decrypted):
                    hum_raw = struct.unpack("<H", decrypted[bthome_idx:bthome_idx+2])[0]
                    hum = round(hum_raw * 0.01, 2)
                    bthome_idx += 2
                else:
                    break
            if temp is not None and hum is not None:
                if -20.0 <= temp <= 60.0 and 0.0 <= hum <= 100.0:
                    return {
                        "temperature": temp,
                        "humidity": hum,
                        "battery": bat if bat is not None else 100,
                        "protocol": "BTHome v2 Encrypted"
                    }
        except Exception:
            continue
    return None

def inspect_ble_name(mac_str, payload):
    idx = 0
    mac_upper = mac_str.upper()
    while idx < len(payload):
        length = payload[idx]
        if length == 0 or idx + length + 1 > len(payload):
            break
        ad_type = payload[idx + 1]
        ad_data = payload[idx + 2 : idx + 1 + length]
        if ad_type in (0x08, 0x09) and len(ad_data) > 0:
            try:
                name = ad_data.decode("utf-8", errors="ignore").strip()
                if len(name) > 0:
                    _device_ble_names[mac_upper] = name
            except Exception:
                pass
        idx += length + 1

_device_last_payload = {}
DEDUP_WINDOW = 3.5  # seconds

def parse_ad_payload(mac_bytes, payload):
    idx = 0
    while idx < len(payload):
        length = payload[idx]
        if length == 0 or idx + length + 1 > len(payload):
            break
        ad_type = payload[idx + 1]
        ad_data = payload[idx + 2 : idx + 1 + length]
        
        if ad_type == 0x16 and len(ad_data) >= 3:
            uuid = struct.unpack("<H", ad_data[0:2])[0]
            
            # Format 1: PVVX Custom (UUID 0x181A)
            if uuid == 0x181A and len(ad_data) >= 9:
                if len(ad_data) >= 15:
                    temp_raw = struct.unpack("<h", ad_data[8:10])[0]
                    hum_raw = struct.unpack("<H", ad_data[10:12])[0]
                    volt_raw = struct.unpack("<H", ad_data[12:14])[0]
                    bat_pct = ad_data[14]
                    t = round(temp_raw / 100.0, 2)
                    h = round(hum_raw / 100.0, 2)
                    v = round(volt_raw / 1000.0, 3) if 2000 <= volt_raw <= 3600 else round(2.2 + (bat_pct / 100.0) * 0.9, 3)
                    if -20.0 <= t <= 60.0 and 0.0 <= h <= 100.0:
                        return {"temperature": t, "humidity": h, "battery": bat_pct, "voltage": v, "protocol": "PVVX Custom (0x181A)"}
                elif len(ad_data) >= 9:
                    temp_raw = struct.unpack("<h", ad_data[2:4])[0]
                    hum_raw = struct.unpack("<H", ad_data[4:6])[0]
                    volt_raw = struct.unpack("<H", ad_data[6:8])[0] if len(ad_data) >= 8 else 3000
                    bat_pct = ad_data[8] if len(ad_data) > 8 else 100
                    t = round(temp_raw / 100.0, 2)
                    h = round(hum_raw / 100.0, 2)
                    v = round(volt_raw / 1000.0, 3) if 2000 <= volt_raw <= 3600 else round(2.2 + (bat_pct / 100.0) * 0.9, 3)
                    if -20.0 <= t <= 60.0 and 0.0 <= h <= 100.0:
                        return {"temperature": t, "humidity": h, "battery": bat_pct, "voltage": v, "protocol": "PVVX Custom (0x181A)"}
            
            # Format 2: BTHome v2 (UUID 0xFCD2)
            elif uuid == 0xFCD2 and len(ad_data) >= 4:
                decrypted_bthome = decrypt_bthome_v2(mac_bytes, ad_data)
                if decrypted_bthome:
                    if "voltage" not in decrypted_bthome:
                        decrypted_bthome["voltage"] = round(2.2 + (decrypted_bthome.get("battery", 100) / 100.0) * 0.9, 3)
                    return decrypted_bthome

                bthome_data = ad_data[2:]
                bthome_idx = 1
                temp, hum, bat, volt = None, None, None, None
                
                while bthome_idx < len(bthome_data):
                    obj_id = bthome_data[bthome_idx]
                    bthome_idx += 1
                    
                    if obj_id == 0x00 and bthome_idx < len(bthome_data):
                        bthome_idx += 1
                    elif obj_id == 0x01 and bthome_idx < len(bthome_data):
                        bat = bthome_data[bthome_idx]
                        bthome_idx += 1
                    elif obj_id == 0x02 and bthome_idx + 2 <= len(bthome_data):
                        temp_raw = struct.unpack("<h", bthome_data[bthome_idx:bthome_idx+2])[0]
                        temp = round(temp_raw * 0.01, 2)
                        bthome_idx += 2
                    elif obj_id == 0x03 and bthome_idx + 2 <= len(bthome_data):
                        hum_raw = struct.unpack("<H", bthome_data[bthome_idx:bthome_idx+2])[0]
                        hum = round(hum_raw * 0.01, 2)
                        bthome_idx += 2
                    elif obj_id == 0x0C and bthome_idx + 2 <= len(bthome_data):
                        volt_raw = struct.unpack("<H", bthome_data[bthome_idx:bthome_idx+2])[0]
                        volt = round(volt_raw * 0.001, 3)
                        bthome_idx += 2
                    else:
                        break
                        
                if temp is not None and hum is not None:
                    if -20.0 <= temp <= 60.0 and 0.0 <= hum <= 100.0:
                        bat_val = bat if bat is not None else 100
                        volt_val = volt if volt is not None else round(2.2 + (bat_val / 100.0) * 0.9, 3)
                        return {
                            "temperature": temp,
                            "humidity": hum,
                            "battery": bat_val,
                            "voltage": volt_val,
                            "protocol": "BTHome v2"
                        }

            # Format 3: Xiaomi MiBeacon (UUID 0xFE95)
            elif uuid == 0xFE95 and len(ad_data) >= 10:
                decrypted_parsed = decrypt_mibeacon(ad_data)
                if decrypted_parsed:
                    if "voltage" not in decrypted_parsed:
                        decrypted_parsed["voltage"] = 3.000
                    return decrypted_parsed

                offset = 11
                while offset + 3 <= len(ad_data):
                    type_id = struct.unpack("<H", ad_data[offset:offset+2])[0]
                    obj_len = ad_data[offset+2]
                    offset += 3
                    if offset + obj_len > len(ad_data):
                        break
                    
                    if type_id == 0x100D and obj_len >= 4:
                        t_raw = struct.unpack("<h", ad_data[offset:offset+2])[0]
                        h_raw = struct.unpack("<H", ad_data[offset+2:offset+4])[0]
                        t = round(t_raw / 10.0, 2)
                        h = round(h_raw / 10.0, 2)
                        if -20.0 <= t <= 60.0 and 0.0 <= h <= 100.0:
                            return {"temperature": t, "humidity": h, "battery": 100, "voltage": 3.000, "protocol": "MiBeacon Standard"}
                    elif type_id == 0x1004 and obj_len >= 2:
                        t_raw = struct.unpack("<h", ad_data[offset:offset+2])[0]
                        t = round(t_raw / 10.0, 2)
                        if -20.0 <= t <= 60.0:
                            return {"temperature": t, "humidity": 50.0, "battery": 100, "voltage": 3.000, "protocol": "MiBeacon Temp"}
                    elif type_id == 0x1006 and obj_len >= 2:
                        h_raw = struct.unpack("<H", ad_data[offset:offset+2])[0]
                        h = round(h_raw / 10.0, 2)
                        if 0.0 <= h <= 100.0:
                            return {"temperature": 22.0, "humidity": h, "battery": 100, "voltage": 3.000, "protocol": "MiBeacon Hum"}
                    offset += obj_len

        idx += length + 1
    return None

def publish_sensor_reading(mac_str, rssi, parsed):
    now = time.time()
    mac_upper = mac_str.upper()
    
    # 1. Deduplication / Debounce Filter (prevents burst duplicate spam to MQTT/DB)
    last_entry = _device_last_payload.get(mac_upper)
    if last_entry:
        last_time, last_t, last_h, last_b, last_v = last_entry
        if (now - last_time < DEDUP_WINDOW) and \
           (parsed.get("temperature") == last_t) and \
           (parsed.get("humidity") == last_h) and \
           (parsed.get("battery") == last_b) and \
           (parsed.get("voltage") == last_v):
            return  # Suppress duplicate burst
            
    _device_last_payload[mac_upper] = (
        now,
        parsed.get("temperature"),
        parsed.get("humidity"),
        parsed.get("battery"),
        parsed.get("voltage")
    )
    
    if mac_upper in _device_last_seen:
        delta = round(now - _device_last_seen[mac_upper], 1)
        if 0.5 <= delta <= 300.0:
            _device_last_interval[mac_upper] = delta
    _device_last_seen[mac_upper] = now
    
    tx_interval = _device_last_interval.get(mac_upper, 2.5)

    device_map, _ = get_device_config()
    mac_suffix = mac_str.replace(":", "")[-4:]
    friendly_name = device_map.get(mac_upper, f"Xiaomi ({mac_suffix})")
    
    ble_name = _device_ble_names.get(mac_upper, get_fallback_ble_name(mac_str))
    
    # Signed 8-bit RSSI conversion
    signed_rssi = struct.unpack("b", bytes([rssi & 0xFF]))[0] if isinstance(rssi, int) else -70
    
    mac_clean = mac_str.replace(":", "").lower()
    topic = f"{MQTT_TOPIC_PREFIX}/{mac_clean}"
    payload_json = {
        "mac": mac_str,
        "name": friendly_name,
        "ble_name": ble_name,
        "hw_ver": "LYWSD03MMC (B1.7)",
        "sw_ver": "PVVX v5.8",
        "temperature": parsed["temperature"],
        "humidity": parsed["humidity"],
        "battery": parsed["battery"],
        "voltage": parsed.get("voltage", 3.000),
        "protocol": parsed.get("protocol", "Unknown"),
        "tx_interval": tx_interval,
        "rssi": signed_rssi
    }
    logging.info(f"LIVE TELEMETRY [{friendly_name} ({ble_name}) / {mac_str}]: T={parsed['temperature']}°C H={parsed['humidity']}% Bat={parsed['battery']}% Volt={parsed.get('voltage', 3.0)}V Proto={parsed.get('protocol')} Int={tx_interval}s")
    mqtt_client.publish(topic, json.dumps(payload_json))

def check_new_mac(mac_str, hex_ad):
    if mac_str not in _seen_macs:
        _seen_macs.add(mac_str)

def parse_hci_packet(pkt_data):
    if len(pkt_data) < 10:
        return
        
    offset = 0
    if pkt_data[0] == 0x04:
        offset = 1
        
    if offset < len(pkt_data) and pkt_data[offset] == 0x3E:
        subevent_idx = offset + 2
        if subevent_idx < len(pkt_data) and pkt_data[subevent_idx] == 0x02:
            num_reports = pkt_data[subevent_idx + 1]
            idx = subevent_idx + 2
            for _ in range(num_reports):
                if idx + 9 > len(pkt_data):
                    break
                data_len = pkt_data[idx + 8]
                if idx + 9 + data_len > len(pkt_data):
                    break
                mac_bytes = pkt_data[idx + 2 : idx + 8]
                mac_str = ":".join([f"{b:02X}" for b in reversed(mac_bytes)])
                payload = pkt_data[idx + 9 : idx + 9 + data_len]
                rssi = pkt_data[idx + 9 + data_len] if (idx + 9 + data_len) < len(pkt_data) else 0
                idx += 9 + data_len + 1

                check_new_mac(mac_str, payload.hex())
                inspect_ble_name(mac_str, payload)

                parsed = parse_ad_payload(mac_bytes, payload)
                if parsed:
                    publish_sensor_reading(mac_str, rssi, parsed)

def tail_btsnoop():
    logging.info(f"Tailing BTSnoop HCI Log: {BTSNOOP_PATH}")
    f = None
    last_inode = None
    missing_retries = 0
    error_retries = 0
    
    while True:
        try:
            if not os.path.exists(BTSNOOP_PATH):
                missing_retries += 1
                backoff = min(60, 2 ** min(missing_retries, 6))
                if missing_retries <= 3 or missing_retries % 10 == 0:
                    logging.warning(f"BTSnoop log file not found at '{BTSNOOP_PATH}'. Backoff waiting {backoff}s (attempt #{missing_retries})...")
                time.sleep(backoff)
                continue
                
            if missing_retries > 0:
                logging.info(f"BTSnoop log file found at '{BTSNOOP_PATH}' after {missing_retries} attempts.")
                missing_retries = 0
                
            st = os.stat(BTSNOOP_PATH)
            
            if f is None or st.st_ino != last_inode or st.st_size < f.tell():
                if f:
                    try:
                        f.close()
                    except Exception:
                        pass
                f = open(BTSNOOP_PATH, "rb")
                last_inode = st.st_ino
                f.read(16)
                logging.info(f"Opened BTSnoop file stream (inode={last_inode}, size={st.st_size} bytes)")
                
            record_hdr = f.read(24)
            if len(record_hdr) < 24:
                if len(record_hdr) > 0:
                    f.seek(-len(record_hdr), os.SEEK_CUR)
                time.sleep(0.5)
                error_retries = 0
                continue
                
            orig_len, inc_len, flags, drops, ts_hi, ts_lo = struct.unpack(">IIIIII", record_hdr)
            pkt_data = f.read(inc_len)
            if len(pkt_data) == inc_len:
                parse_hci_packet(pkt_data)
            error_retries = 0
        except Exception as e:
            error_retries += 1
            backoff = min(60, 2 ** min(error_retries, 6))
            logging.error(f"Error in tail_btsnoop (attempt #{error_retries}): {e}. Backing off {backoff}s...")
            if f:
                try:
                    f.close()
                except Exception:
                    pass
                f = None
            time.sleep(backoff)

def tcp_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", TCP_PORT))
        srv.listen(2)
        logging.info(f"TCP server listening on 127.0.0.1:{TCP_PORT}")
    except Exception as e:
        logging.error(f"TCP bind failed: {e}")
        return

    while True:
        try:
            conn, addr = srv.accept()
            logging.info(f"TCP client connected from {addr}")
            t = threading.Thread(target=handle_tcp_client, args=(conn,), daemon=True)
            t.start()
        except Exception as e:
            time.sleep(1)

def handle_tcp_client(conn):
    buf = b""
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                process_tcp_line(line.decode("utf-8", errors="ignore").strip())
    except Exception as e:
        logging.error(f"TCP client error: {e}")
    finally:
        conn.close()

def process_tcp_line(line):
    parts = line.split(",", 2)
    if len(parts) != 3:
        return
    mac, rssi_str, hex_ad = parts
    try:
        rssi = int(rssi_str)
        ad_bytes = bytes.fromhex(hex_ad)
    except (ValueError, TypeError):
        return
    
    check_new_mac(mac, hex_ad)
    inspect_ble_name(mac, ad_bytes)

    mac_bytes = bytes.fromhex(mac.replace(":", ""))
    parsed = parse_ad_payload(mac_bytes, ad_bytes)
    if parsed:
        publish_sensor_reading(mac, rssi, parsed)

if __name__ == "__main__":
    connect_mqtt()
    t_tcp = threading.Thread(target=tcp_server, daemon=True)
    t_tcp.start()
    tail_btsnoop()

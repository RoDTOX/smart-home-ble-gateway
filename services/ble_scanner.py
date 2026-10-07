#!/usr/bin/env python3
"""
Samsung A6 BLE Scanner — Direct HCI Socket Approach (requires root)
Sends LE_Set_Scan_Parameters + LE_Set_Scan_Enable HCI commands directly
to the Bluetooth controller, then reads LE Advertising Report events.
Publishes decoded Xiaomi PVVX/BTHome sensor data to MQTT.
"""

import os, sys, time, json, struct, socket, logging
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DEVICES_CONFIG = os.path.expanduser("~/smart-home-ble-gateway/config/devices.json")
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC_PREFIX = "home/sensors/ble"

# HCI constants
AF_BLUETOOTH = 31
BTPROTO_HCI = 1
HCI_FILTER = 2
SOL_HCI = 0

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="a6_ble_scanner")

_last_config_check = 0
_cached_device_map = {}

def get_device_mappings():
    global _last_config_check, _cached_device_map
    now = time.time()
    if now - _last_config_check > 5:
        _last_config_check = now
        if os.path.exists(DEVICES_CONFIG):
            try:
                with open(DEVICES_CONFIG, "r") as f:
                    _cached_device_map = json.load(f)
            except Exception as e:
                logging.error(f"Config load error: {e}")
    return _cached_device_map

def connect_mqtt():
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        logging.info("MQTT connected")
    except Exception as e:
        logging.error(f"MQTT failed: {e}")

def parse_ad_payload(payload):
    """Parse BLE advertising payload for PVVX (0x181A) or BTHome v2 (0xFCD2)."""
    idx = 0
    while idx < len(payload):
        if idx >= len(payload):
            break
        length = payload[idx]
        if length == 0 or idx + length + 1 > len(payload):
            break
        ad_type = payload[idx + 1]
        ad_data = payload[idx + 2 : idx + 1 + length]

        if ad_type == 0x16 and len(ad_data) >= 3:
            uuid = struct.unpack("<H", ad_data[0:2])[0]

            # PVVX Custom format (UUID 0x181A)
            if uuid == 0x181A and len(ad_data) >= 15:
                temp_raw = struct.unpack("<h", ad_data[8:10])[0]
                hum_raw = struct.unpack("<H", ad_data[10:12])[0]
                bat_pct = ad_data[14]
                return {
                    "temperature": round(temp_raw / 100.0, 2),
                    "humidity": round(hum_raw / 100.0, 2),
                    "battery": bat_pct
                }

            # BTHome v2 (UUID 0xFCD2)
            elif uuid == 0xFCD2 and len(ad_data) >= 4:
                bthome_data = ad_data[2:]
                bi = 1
                temp, hum, bat = None, None, None
                while bi < len(bthome_data):
                    obj_id = bthome_data[bi]
                    bi += 1
                    if obj_id == 0x01 and bi < len(bthome_data):
                        bat = bthome_data[bi]; bi += 1
                    elif obj_id == 0x02 and bi + 2 <= len(bthome_data):
                        temp = round(struct.unpack("<h", bthome_data[bi:bi+2])[0] * 0.01, 2); bi += 2
                    elif obj_id == 0x03 and bi + 2 <= len(bthome_data):
                        hum = round(struct.unpack("<H", bthome_data[bi:bi+2])[0] * 0.01, 2); bi += 2
                    else:
                        break
                if temp is not None and hum is not None:
                    return {"temperature": temp, "humidity": hum, "battery": bat or 100}
        idx += length + 1
    return None

def publish_sensor(mac_str, rssi, parsed):
    device_map = get_device_mappings()
    mac_suffix = mac_str.replace(":", "")[-4:]
    friendly_name = device_map.get(mac_str.upper(), f"Xiaomi ({mac_suffix})")
    mac_clean = mac_str.replace(":", "").lower()
    topic = f"{MQTT_TOPIC_PREFIX}/{mac_clean}"
    payload_json = {
        "mac": mac_str,
        "name": friendly_name,
        "temperature": parsed["temperature"],
        "humidity": parsed["humidity"],
        "battery": parsed["battery"],
        "rssi": rssi if rssi < 128 else rssi - 256
    }
    logging.info(f"SENSOR [{friendly_name}] Temp={parsed['temperature']}°C Hum={parsed['humidity']}% Bat={parsed['battery']}%")
    mqtt_client.publish(topic, json.dumps(payload_json))

def open_hci_socket():
    """Open raw HCI socket bound to hci0 (dev_id=0)."""
    sock = socket.socket(AF_BLUETOOTH, socket.SOCK_RAW, BTPROTO_HCI)
    # Bind to hci0
    sock.bind((0,))  # dev_id = 0

    # Set HCI filter to accept LE Meta Events (0x3E)
    # struct hci_filter { uint32_t type_mask; uint32_t event_mask[2]; uint16_t opcode; }
    # type_mask: bit 4 = HCI_EVENT_PKT (0x10)
    # event_mask: bit 0x3E = 62 => word1 bit 30
    type_mask = 1 << 4  # HCI_EVENT_PKT = 0x04, bit position = 4
    event_mask_lo = (1 << 30)  # bit 62 % 32 = 30 for event code 0x3E
    event_mask_hi = (1 << 30)  # also set in upper word for safety
    flt = struct.pack("<IIIh", type_mask, event_mask_lo, event_mask_hi, 0)
    sock.setsockopt(SOL_HCI, HCI_FILTER, flt)
    return sock

def hci_send_cmd(sock, ogf, ocf, params=b''):
    """Send an HCI command."""
    opcode = (ocf & 0x03FF) | ((ogf & 0x3F) << 10)
    pkt = struct.pack("<BHB", 0x01, opcode, len(params)) + params
    sock.send(pkt)

def start_le_scan(sock):
    """Send LE Set Scan Parameters + LE Set Scan Enable."""
    # LE Set Scan Parameters: OGF=0x08, OCF=0x000B
    # Type=0x01(active), Interval=0x0010, Window=0x0010, OwnAddrType=0, FilterPolicy=0
    hci_send_cmd(sock, 0x08, 0x000B, struct.pack("<BHHBB", 0x00, 0x0060, 0x0030, 0x00, 0x00))
    time.sleep(0.1)
    # LE Set Scan Enable: OGF=0x08, OCF=0x000C
    # Enable=1, FilterDuplicates=0
    hci_send_cmd(sock, 0x08, 0x000C, struct.pack("<BB", 0x01, 0x00))
    logging.info("LE Scan enabled on hci0")

def process_hci_events(sock):
    """Read HCI events and process LE Advertising Reports."""
    while True:
        try:
            data = sock.recv(1024)
            if not data or len(data) < 4:
                continue

            # HCI Event packet: [0x04] [event_code] [param_len] [params...]
            if data[0] != 0x04:
                continue
            event_code = data[1]
            if event_code != 0x3E:  # LE Meta Event
                continue

            # LE Meta: [subevent] [...]
            subevent = data[3]
            if subevent != 0x02:  # LE Advertising Report
                continue

            num_reports = data[4]
            idx = 5
            for _ in range(num_reports):
                if idx + 8 > len(data):
                    break
                # event_type = data[idx]
                # addr_type = data[idx + 1]
                mac_bytes = data[idx + 2 : idx + 8]
                mac_str = ":".join(f"{b:02X}" for b in reversed(mac_bytes))
                data_len = data[idx + 8]
                ad_payload = data[idx + 9 : idx + 9 + data_len]
                rssi_idx = idx + 9 + data_len
                rssi = data[rssi_idx] if rssi_idx < len(data) else 0
                idx = rssi_idx + 1

                parsed = parse_ad_payload(ad_payload)
                if parsed:
                    publish_sensor(mac_str, rssi, parsed)
        except Exception as e:
            logging.error(f"HCI read error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    connect_mqtt()
    try:
        sock = open_hci_socket()
        start_le_scan(sock)
        process_hci_events(sock)
    except PermissionError:
        logging.error("Need root. Run with: su -c python3 ble_scanner.py")
        sys.exit(1)
    except OSError as e:
        logging.error(f"HCI socket error: {e}")
        logging.info("Falling back to btsnoop_hci.log tailing...")
        # Fallback: tail the btsnoop log (passive, only works if another app scans)
        from btsnoop_scanner import tail_btsnoop
        tail_btsnoop()

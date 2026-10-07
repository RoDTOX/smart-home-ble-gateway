import json
import paho.mqtt.client as mqtt

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.connect("127.0.0.1", 1883)

payload = {
    "mac": "A4:C1:38:84:A1:E8",
    "name": "Kids Room",
    "temperature": 23.8,
    "humidity": 52.0,
    "battery": 98,
    "rssi": -68
}

c.publish("home/sensors/ble/a4c13884a1e8", json.dumps(payload))
c.disconnect()
print("Published reading for Kids Room [A4:C1:38:84:A1:E8]: 23.8°C, 52.0%")

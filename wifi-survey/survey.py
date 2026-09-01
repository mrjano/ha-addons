#!/usr/bin/env python3
"""wifi-survey: escaneo pasivo de la radio -> sensores MQTT con discovery.

Cada ciclo hace `iw scan passive` (escuchar beacons, sin asociarse ni emitir)
y publica:
  - por cada BSSID del SSID propio: RSSI y canal, como device propio en HA
  - agregados: nº de vecinos y el vecino más fuerte (con attrs)

Los sensores llevan expire_after = 3 ciclos: si un AP desaparece del escaneo
(radar en DFS, reinicio), su sensor pasa a 'unavailable' solo, sin publicar
valores nulos. La desaparición ES el dato.
"""
import json
import os
import re
import subprocess
import time

import paho.mqtt.client as mqtt

IFACE = os.environ.get("IFACE", "wlan0")
HOME_SSID = os.environ["HOME_SSID"]
EVERY = int(os.environ.get("SCAN_INTERVAL", "120"))

AP_NAMES = {}
for line in os.environ.get("AP_NAMES", "").splitlines():
    if "=" in line:
        b, n = line.split("=", 1)
        AP_NAMES[b.strip().lower()] = n.strip()

DISC = "homeassistant"       # prefijo de MQTT discovery
BASE = "wifisurvey"
AVAIL = f"{BASE}/availability"
EXPIRE = EVERY * 3


def sh(cmd, timeout=90):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def freq_to_channel(mhz):
    if 2412 <= mhz <= 2484:
        return 14 if mhz == 2484 else (mhz - 2407) // 5
    if 5000 < mhz < 5925:
        return (mhz - 5000) // 5
    return None


SIG_RE = re.compile(r"signal: (-?[\d.]+) dBm")
FREQ_RE = re.compile(r"freq: ([\d.]+)")
SSID_RE = re.compile(r"^\s+SSID: (.*)$", re.M)
DS_RE = re.compile(r"DS Parameter set: channel (\d+)")
HT_RE = re.compile(r"\* primary channel: (\d+)")


def scan():
    """Un escaneo pasivo. Devuelve None si iw falló (p.ej. -EBUSY del brcmfmac),
    para distinguirlo de un escaneo válido que no vio nada."""
    sh(["ip", "link", "set", IFACE, "up"], timeout=10)
    out = sh(["iw", "dev", IFACE, "scan", "passive"], timeout=90)
    if not out.strip():
        return None
    aps = []
    for blk in re.split(r"(?m)^BSS ", out)[1:]:
        bssid = blk[:17].lower()
        sig = SIG_RE.search(blk)
        frq = FREQ_RE.search(blk)
        ssid = SSID_RE.search(blk)
        ch = DS_RE.search(blk) or HT_RE.search(blk)
        freq = int(float(frq.group(1))) if frq else None
        aps.append({
            "bssid": bssid,
            "ssid": (ssid.group(1).strip() if ssid else "") or None,
            "rssi": round(float(sig.group(1))) if sig else None,
            "channel": int(ch.group(1)) if ch else (freq_to_channel(freq) if freq else None),
            "band": ("2GHz" if freq < 3000 else "5GHz") if freq else None,
        })
    return aps


# ---------------------------------------------------------------- MQTT

# paho 2.x exige declarar la versión del API de callbacks; paho 1.x no la tiene.
try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="wifi-survey")
except AttributeError:
    client = mqtt.Client(client_id="wifi-survey")
client.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASS"])
client.will_set(AVAIL, "offline", retain=True)
client.connect(os.environ["MQTT_HOST"], int(os.environ["MQTT_PORT"]))
client.loop_start()
client.publish(AVAIL, "online", retain=True)


def announce_ap(bssid):
    """Discovery retenido: HA crea el device y sus sensores al primer beacon."""
    uid = bssid.replace(":", "")
    name = AP_NAMES.get(bssid, f"AP {bssid[-5:]}")
    dev = {"identifiers": [f"wifisurvey_{uid}"], "name": f"WiFi {name}",
           "manufacturer": "wifi-survey", "model": HOME_SSID}
    state_t = f"{BASE}/{uid}/state"
    sensors = {
        "rssi": {"name": "RSSI", "unit_of_measurement": "dBm",
                 "device_class": "signal_strength", "state_class": "measurement"},
        "channel": {"name": "Canal", "icon": "mdi:radio-tower"},
    }
    for key, extra in sensors.items():
        cfg = {"state_topic": state_t,
               "value_template": "{{ value_json.%s }}" % key,
               "json_attributes_topic": state_t,
               "unique_id": f"wifisurvey_{uid}_{key}",
               "availability_topic": AVAIL,
               "expire_after": EXPIRE,
               "device": dev, **extra}
        client.publish(f"{DISC}/sensor/{BASE}/{uid}_{key}/config",
                       json.dumps(cfg), retain=True)


def announce_aggregates():
    dev = {"identifiers": ["wifisurvey_agg"], "name": "WiFi Survey (despacho)",
           "manufacturer": "wifi-survey"}
    for uid, extra in {
        "neighbors": {"name": "Vecinos", "icon": "mdi:access-point-network",
                      "state_class": "measurement"},
        "strongest_neighbor": {"name": "Vecino más fuerte", "unit_of_measurement": "dBm",
                               "device_class": "signal_strength",
                               "state_class": "measurement"},
    }.items():
        cfg = {"state_topic": f"{BASE}/{uid}/state",
               "value_template": "{{ value_json.value }}",
               "json_attributes_topic": f"{BASE}/{uid}/state",
               "unique_id": f"wifisurvey_{uid}",
               "availability_topic": AVAIL,
               "expire_after": EXPIRE,
               "device": dev, **extra}
        client.publish(f"{DISC}/sensor/{BASE}/{uid}/config",
                       json.dumps(cfg), retain=True)


# ---------------------------------------------------------------- main

announced = set()
announce_aggregates()
print(f"wifi-survey arrancado: {IFACE}, cada {EVERY}s, SSID propio {HOME_SSID}", flush=True)

while True:
    t0 = time.time()
    aps = scan()
    if aps is None:
        # brcmfmac ocupado o interfaz caída: reintento corto, no ciclo entero
        print("scan falló, reintento en 15s", flush=True)
        time.sleep(15)
        continue

    home = [a for a in aps if a["ssid"] == HOME_SSID]
    neigh = [a for a in aps if a["ssid"] != HOME_SSID and a["rssi"] is not None]

    for ap in home:
        if ap["bssid"] not in announced:
            announce_ap(ap["bssid"])
            announced.add(ap["bssid"])
        uid = ap["bssid"].replace(":", "")
        client.publish(f"{BASE}/{uid}/state", json.dumps(ap))

    strongest = max(neigh, key=lambda a: a["rssi"], default=None)
    client.publish(f"{BASE}/neighbors/state", json.dumps({
        "value": len(neigh),
        # co-canal con los APs propios: los que se reparten el mismo aire
        "co_channel": len([n for n in neigh
                           if n["channel"] in {a["channel"] for a in home}]),
    }))
    if strongest:
        client.publish(f"{BASE}/strongest_neighbor/state", json.dumps({
            "value": strongest["rssi"], "ssid": strongest["ssid"],
            "channel": strongest["channel"], "band": strongest["band"],
        }))

    vis = ", ".join(f"{a['ssid'] or '?'} ch{a['channel']} {a['rssi']}dBm" for a in home)
    print(f"[{time.strftime('%H:%M:%S')}] propios: {vis or 'NINGUNO'} | "
          f"vecinos: {len(neigh)}", flush=True)

    time.sleep(max(10, EVERY - (time.time() - t0)))

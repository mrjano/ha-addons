# WiFi Survey

Escaneo **pasivo** de la radio de la Pi (`iw scan passive`) cada N segundos, sin
asociarse a ninguna red: `eth0` sigue siendo la única ruta y Home Assistant no
pasa a depender del WiFi que precisamente se quiere vigilar.

Publica por MQTT discovery:

- **Por cada BSSID del SSID propio** (`home_ssid`): RSSI (dBm) y canal, como
  device propio en HA. Sirve para ver la señal de cada AP *desde el despacho*,
  incluidos los canales DFS de 5 GHz (100/104) que un ESP32 no puede ver.
- **Agregados**: nº de redes vecinas (attr `co_channel`: cuántas comparten canal
  con los APs propios) y RSSI del vecino más fuerte (attrs: ssid, canal, banda).

Si un AP desaparece del escaneo (radar en DFS, reinicio), su sensor pasa a
`unavailable` a los 3 ciclos (`expire_after`). La desaparición es el dato.

## Requisitos

- Add-on **Mosquitto broker** instalado y arrancado (usa su service API).
- La radio interna de la Pi libre (sin configuración WiFi en HAOS).

## Opciones

| opción | por defecto | qué es |
|---|---|---|
| `home_ssid` | `ASUS_28` | SSID propio: sus BSSID se convierten en devices |
| `interface` | `wlan0` | interfaz a escanear |
| `scan_interval` | `120` | segundos entre escaneos |
| `ap_names` | `[]` | etiquetas `bssid=nombre` para los APs propios |

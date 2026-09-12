#!/usr/bin/with-contenv bashio
# Puente entre la config del add-on / la service API y el script de Python.
set -e

# Mosquitto puede tardar en registrarse como proveedor del servicio mqtt. Al
# restaurar el backup del 2026-09-12 este add-on arrancó a las 23:48 y Mosquitto
# no quedó registrado hasta las 23:57: nueve minutos. Comprobarlo una sola vez y
# morir con FATAL dejaba el add-on parado hasta que alguien lo levantara a mano,
# y con él el survey del despacho. Así que esperamos.
for intento in $(seq 1 60); do
    if bashio::services.available mqtt; then
        break
    fi
    bashio::log.warning "Aún no hay broker MQTT; reintento ${intento}/60 en 10 s."
    sleep 10
done

if ! bashio::services.available mqtt; then
    bashio::log.fatal "10 minutos sin broker MQTT. ¿Está Mosquitto instalado y arrancado?"
    exit 1
fi

export MQTT_HOST="$(bashio::services mqtt 'host')"
export MQTT_PORT="$(bashio::services mqtt 'port')"
export MQTT_USER="$(bashio::services mqtt 'username')"
export MQTT_PASS="$(bashio::services mqtt 'password')"

export HOME_SSID="$(bashio::config 'home_ssid')"
export IFACE="$(bashio::config 'interface')"
export SCAN_INTERVAL="$(bashio::config 'scan_interval')"
# bashio imprime las listas un elemento por línea; Python hace splitlines().
export AP_NAMES="$(bashio::config 'ap_names')"

bashio::log.info "wifi-survey: ${IFACE}, SSID propio '${HOME_SSID}', cada ${SCAN_INTERVAL}s"
exec python3 -u /survey.py

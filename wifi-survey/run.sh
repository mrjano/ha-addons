#!/usr/bin/with-contenv bashio
# Puente entre la config del add-on / la service API y el script de Python.
set -e

if ! bashio::services.available mqtt; then
    bashio::log.fatal "No hay broker MQTT. Instala el add-on Mosquitto primero."
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

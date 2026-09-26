#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env. Replace every placeholder secret before starting services."
fi

if [[ ! -s mosquitto/config/passwords.runtime ]]; then
  read -r -p "MQTT device/API username [water-api]: " mqtt_user
  mqtt_user=${mqtt_user:-water-api}
  read -r -s -p "MQTT password: " mqtt_password
  echo
  if [[ -z "$mqtt_password" ]]; then
    echo "An MQTT password is required." >&2
    exit 1
  fi
  docker run --rm --user 1883:1883 -v "$PWD/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2.0 \
    mosquitto_passwd -b -c /mosquitto/config/passwords.runtime "$mqtt_user" "$mqtt_password"
  echo "Created Mosquitto credentials. Use the same values in .env and firmware/esp32/include/config.h."
fi

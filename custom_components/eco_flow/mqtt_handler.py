"""
mqtt_handler.py – A comprehensive MQTT handler for EcoFlow,
optimized for clarity and thread safety, delegating async updates to coordinator.
"""

import logging
import asyncio
import json
import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)

class EcoFlowMQTTHandler:
    """Manages the MQTT connection to EcoFlow broker and merges incoming data into coordinator."""

    def __init__(self, hass, coordinator):
        self.hass = hass
        self.coordinator = coordinator
        self.client = None
        self.connected = False
        self.message_count = 0

        cert_info = self.coordinator.mqtt_cert_data
        self.mqtt_host = cert_info.get("url", "mqtt.ecoflow.com")
        self.mqtt_port = int(cert_info.get("port", 8883))
        self.mqtt_user = cert_info.get("certificateAccount", "open-xxxx")
        self.mqtt_pass = cert_info.get("certificatePassword", "xxxx")
        self.use_tls = cert_info.get("protocol", "mqtts") == "mqtts"

        self.sn = self.coordinator.device_sn
        self.certificate_account = self.mqtt_user

        self.topics_to_subscribe = ["quota"]

    def connect(self):
        """Connect to EcoFlow MQTT broker in a separate thread."""
        self.client = mqtt.Client()
        self.client.username_pw_set(self.mqtt_user, self.mqtt_pass)

        if self.use_tls:
            self.client.tls_set()
            _LOGGER.debug("Using TLS for MQTT (protocol: mqtts).")

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        try:
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            _LOGGER.info("Connecting to EcoFlow MQTT broker at %s:%s", self.mqtt_host, self.mqtt_port)
        except Exception as exc:
            _LOGGER.error("Failed to connect to MQTT broker: %s", exc)

        self.client.loop_start()

    def stop(self):
        """Stop MQTT gracefully."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            _LOGGER.info("MQTT client disconnected and loop stopped.")

    def on_connect(self, client, userdata, flags, rc):
        """Callback on successful or failed connection."""
        if rc == 0:
            self.connected = True
            _LOGGER.info("EcoFlow MQTT connected successfully.")
            for topic in self.topics_to_subscribe:
                full_topic = f"/open/{self.certificate_account}/{self.sn}/{topic}"
                client.subscribe(full_topic)
                _LOGGER.info("Subscribed to MQTT topic: %s", full_topic)
        else:
            _LOGGER.error(
                "MQTT connection failed with code %s. Description: %s", rc, self._get_mqtt_error_description(rc)
            )

    def on_disconnect(self, client, userdata, rc):
        """Callback on disconnection."""
        self.connected = False
        if rc == 0:
            _LOGGER.info("MQTT disconnected gracefully.")
        else:
            _LOGGER.warning(
                "MQTT disconnected unexpectedly (rc: %s). Reason: %s", rc, self._get_disconnect_reason(rc)
            )

    def on_message(self, client, userdata, msg):
        """Handle an incoming MQTT message."""
        try:
            payload_json = json.loads(msg.payload.decode("utf-8"))
        except Exception as exc:
            _LOGGER.error("Failed to decode MQTT message on %s: %s", msg.topic, exc)
            return

        _LOGGER.debug("Received MQTT message on %s: %s", msg.topic, payload_json)

        if not payload_json:
            _LOGGER.warning("Empty MQTT message received on %s", msg.topic)
            return

        data = payload_json.get("params", payload_json)

        if not data:
            _LOGGER.warning("Empty 'params' in MQTT message on %s", msg.topic)
            return

        self.message_count += 1
        _LOGGER.info("Total MQTT messages received: %d", self.message_count)

        self.coordinator.update_mqtt_data(msg.topic, data)

    def _get_mqtt_error_description(self, rc):
        """Map MQTT error codes to descriptions."""
        errors = {
            1: "Unacceptable protocol version",
            2: "Identifier rejected",
            3: "Server unavailable",
            4: "Bad username or password",
            5: "Not authorized",
        }
        return errors.get(rc, "Unknown error")

    def _get_disconnect_reason(self, rc):
        """Map MQTT disconnect codes to reasons."""
        reasons = {
            0: "Graceful disconnect",
            1: "Unexpected error",
            2: "Network error",
            3: "Client closed connection",
        }
        return reasons.get(rc, "Unknown reason")

"""
mqtt_handler.py – A comprehensive MQTT handler for EcoFlow PowerOcean,
auto-using data from coordinator.mqtt_cert_data if present.
Subscribes to all known EcoFlow topics: quota, status, set, set_reply, get, get_reply.
"""

import logging
import asyncio
import json
import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)

class EcoFlowMQTTHandler:
    """Manages the MQTT connection to EcoFlow and merges incoming data into coordinator."""

    def __init__(self, hass, coordinator):
        self.hass = hass
        self.coordinator = coordinator
        self.client = None
        self.loop = asyncio.get_event_loop()
        self.connected = False

        # Read from coordinator.mqtt_cert_data
        cert_info = self.coordinator.mqtt_cert_data
        self.mqtt_host = cert_info.get("url", "mqtt.ecoflow.com")
        self.mqtt_port = int(cert_info.get("port", 8883))
        self.mqtt_user = cert_info.get("certificateAccount", "open-xxxx")
        self.mqtt_pass = cert_info.get("certificatePassword", "xxxx")
        protocol = cert_info.get("protocol", "mqtts")
        self.use_tls = (protocol == "mqtts")

        self.sn = self.coordinator.device_sn
        self.certificate_account = self.mqtt_user

        # EcoFlow doc: topics
        self.topics_to_subscribe = [
            "quota",
            "status",
            "set",
            "set_reply",
            "get",
            "get_reply",
        ]

    def connect(self):
        """Connect to EcoFlow MQTT broker."""
        self.client = mqtt.Client()
        self.client.username_pw_set(self.mqtt_user, self.mqtt_pass)

        if self.use_tls:
            self.client.tls_set()
            _LOGGER.debug("Using TLS for MQTT connection (protocol: mqtts).")

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        _LOGGER.info("Connecting to EcoFlow MQTT broker at %s:%s", self.mqtt_host, self.mqtt_port)

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
            # Subscribe to topics
            for t in self.topics_to_subscribe:
                topic = f"/open/{self.certificate_account}/{self.sn}/{t}"
                client.subscribe(topic)
                _LOGGER.info("Subscribed to MQTT topic: %s", topic)
        else:
            _LOGGER.error("MQTT connection failed with code %s", rc)

    def on_disconnect(self, client, userdata, rc):
        """Callback on disconnection."""
        self.connected = False
        _LOGGER.warning("MQTT disconnected (rc: %s).", rc)

    def on_message(self, client, userdata, msg):
        """Handle an incoming MQTT message."""
        try:
            payload_str = msg.payload.decode("utf-8")
            payload_json = json.loads(payload_str)
        except Exception as exc:
            _LOGGER.error("Failed to decode MQTT message on %s: %s", msg.topic, exc)
            return

        _LOGGER.debug("Received MQTT message on %s: %s", msg.topic, payload_json)

        # EcoFlow often has data in payload_json["params"]
        if "params" in payload_json:
            data = payload_json["params"]
        else:
            data = payload_json

        # Let coordinator merge this new data
        self.coordinator.update_mqtt_data(msg.topic, data)

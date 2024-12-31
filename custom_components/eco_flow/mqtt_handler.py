"""
mqtt_handler.py – A comprehensive MQTT handler for EcoFlow PowerOcean, 
automatically using the data from coordinator.mqtt_cert_data if available.
"""

import logging
import asyncio
import json
import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)

class EcoFlowMQTTHandler:
    """
    Manages the MQTT connection to the EcoFlow broker and merges incoming data
    into the coordinator.
    """

    def __init__(self, hass, coordinator):
        """
        :param hass: HomeAssistant instance
        :param coordinator: EcoFlowDataCoordinator
        """
        self.hass = hass
        self.coordinator = coordinator
        self.client = None
        self.loop = asyncio.get_event_loop()
        self.connected = False

        # After we fetched cert data in coordinator, we can read it here
        cert_info = self.coordinator.mqtt_cert_data
        # If cert_info is empty, fallback to defaults:
        self.mqtt_host = cert_info.get("url", "mqtt.ecoflow.com")
        self.mqtt_port = int(cert_info.get("port", 8883))
        self.mqtt_user = cert_info.get("certificateAccount", "open-xxx")
        self.mqtt_pass = cert_info.get("certificatePassword", "xxx")
        protocol = cert_info.get("protocol", "mqtts")  # e.g. "mqtt", "mqtts"
        self.use_tls = (protocol == "mqtts")

        # device SN
        self.sn = self.coordinator.device_sn
        self.certificate_account = self.mqtt_user

        # Topics from EcoFlow doc
        self.topics_to_subscribe = [
            "quota",
            "status",
            "set",
            "set_reply",
            "get",
            "get_reply",
        ]

    def connect(self):
        """Establish the MQTT connection."""
        self.client = mqtt.Client()

        # Credentials
        self.client.username_pw_set(self.mqtt_user, self.mqtt_pass)

        # TLS if needed
        if self.use_tls:
            self.client.tls_set()
            _LOGGER.debug("Using TLS for MQTT connection (protocol: mqtts).")

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        _LOGGER.info("Connecting to EcoFlow MQTT broker at %s:%s", self.mqtt_host, self.mqtt_port)

        # Start loop
        self.client.loop_start()

    def stop(self):
        """Stop MQTT gracefully."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            _LOGGER.info("MQTT client disconnected and loop stopped.")

    def on_connect(self, client, userdata, flags, rc):
        """Callback when MQTT connection is established."""
        if rc == 0:
            self.connected = True
            _LOGGER.info("MQTT connected successfully.")
            for t in self.topics_to_subscribe:
                topic = f"/open/{self.certificate_account}/{self.sn}/{t}"
                client.subscribe(topic)
                _LOGGER.info("Subscribed to MQTT topic: %s", topic)
        else:
            _LOGGER.error("MQTT connection failed with code %s", rc)

    def on_disconnect(self, client, userdata, rc):
        """Callback when the MQTT client disconnects."""
        self.connected = False
        _LOGGER.warning("MQTT disconnected (rc: %s). Trying reconnect if needed.", rc)
        # paho-mqtt can auto-reconnect, or you could manually handle it.

    def on_message(self, client, userdata, msg):
        """Callback when a message is received on a subscribed topic."""
        try:
            payload_str = msg.payload.decode("utf-8")
            payload_json = json.loads(payload_str)
        except Exception as exc:
            _LOGGER.error("Failed to decode MQTT message on %s: %s", msg.topic, exc)
            return

        _LOGGER.debug("Received MQTT message on %s: %s", msg.topic, payload_json)

        # Often, the data is in payload_json["params"].
        # If absent, we store entire payload.
        if "params" in payload_json:
            data = payload_json["params"]
        else:
            data = payload_json

        # Merge into coordinator
        self.coordinator.update_mqtt_data(msg.topic, data)

import logging
import hmac
import hashlib
import time
import json
import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)

class EcoFlowMQTTHandler:
    """Manages the MQTT connection to EcoFlow broker with proper signature authentication."""

    def __init__(self, hass, coordinator):
        self.hass = hass
        self.coordinator = coordinator
        self.client = None
        self.connected = False
        self.message_count = 0

        cert_info = self.coordinator.mqtt_cert_data
        self.mqtt_host = cert_info.get("url", "mqtt.ecoflow.com")
        self.mqtt_port = int(cert_info.get("port", 8883))
        self.access_key = cert_info.get("accessKey")
        self.secret_key = cert_info.get("secretKey")
        self.device_sn = self.coordinator.device_sn
        self.use_tls = cert_info.get("protocol", "mqtts") == "mqtts"

        self.topics_to_subscribe = ["quota"]

    def generate_signature(self, params, access_key, nonce, timestamp, secret_key):
        """Generate HMAC-SHA256 signature based on the given parameters."""
        param_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        full_string = f"{param_string}&accessKey={access_key}&nonce={nonce}&timestamp={timestamp}"
        signature = hmac.new(
            secret_key.encode('utf-8'),
            full_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def connect(self):
        """Connect to EcoFlow MQTT broker in a separate thread."""
        self.client = mqtt.Client()
        self.client.username_pw_set(self.access_key, self.secret_key)

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
                full_topic = f"/open/{self.access_key}/{self.device_sn}/{topic}"
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

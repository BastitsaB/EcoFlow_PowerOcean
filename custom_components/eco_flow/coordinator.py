"""
coordinator.py – Coordinator for EcoFlow PowerOcean data (REST + MQTT),
with:
 - 5-second polling for normal "all quotas" data
 - 5-minute polling for historical data
 - Automatic fetch of MQTT certificate if needed.
"""

import logging
import time
import hashlib
import hmac
import requests
from datetime import timedelta, datetime

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class EcoFlowDataCoordinator(DataUpdateCoordinator):
    """
    Coordinates data updates from EcoFlow Cloud + merges MQTT updates.
    - Polling for normal (current) data every 5 seconds
    - Historical data only every 5 minutes
    """

    def __init__(self, hass: HomeAssistant, config_entry):
        super().__init__(
            hass,
            _LOGGER,
            name="EcoFlowDataCoordinator",
            update_interval=timedelta(seconds=5)  # Alle 5 Sekunden abrufen
        )
        self._hass = hass
        self._config_entry = config_entry

        data = config_entry.data
        self.access_key = data.get("access_key")
        self.secret_key = data.get("secret_key")
        self.device_sn = data.get("device_sn")
        self.mqtt_enabled = data.get("mqtt_enabled", False)

        self.base_url = "https://api-e.ecoflow.com"

        # Lokale Caches
        self.cloud_data = {}        # "all quotas" etc.
        self.historical_data = {}   # history data
        self.mqtt_data = {}         # merges from MQTT
        self.mqtt_cert_data = {}    # certificate info

        # Speichern, wann wir zuletzt historische Daten geholt haben
        self._last_history_fetch = None
        self._history_interval_sec = 300  # alle 5 Minuten (300 Sekunden)

    async def _async_update_data(self):
        """
        Wird alle 5 Sekunden durch DataUpdateCoordinator aufgerufen.
        1) Normale "all quotas" abrufen
        2) Historische Daten nur alle 5 Minuten
        3) MQTT-Daten mergen
        """
        # 1) "All Quotas" alle 5 Sekunden
        try:
            self.cloud_data = await self._hass.async_add_executor_job(self._fetch_all_quotas)
        except Exception as exc:
            _LOGGER.error("Error fetching normal (all quotas) data: %s", exc)
            raise

        # 2) Historische Daten nur alle 5 Minuten
        need_history = False
        now = datetime.now()
        if not self._last_history_fetch:
            # Noch nie geholt, also beim ersten Mal
            need_history = True
        else:
            # Prüfe, ob schon 5 Minuten vorbei sind
            delta_sec = (now - self._last_history_fetch).total_seconds()
            if delta_sec > self._history_interval_sec:
                need_history = True

        if need_history:
            _LOGGER.debug("Fetching historical data ...")
            try:
                self.historical_data = await self._hass.async_add_executor_job(self._fetch_historical_data)
            except Exception as exc:
                _LOGGER.error("Error fetching historical data: %s", exc)
                # Hier kein raise, damit die normalen Daten trotzdem verfügbar bleiben
            self._last_history_fetch = now

        # 3) Alles in ein Dictionary mergen
        combined_data = {}
        combined_data.update(self.cloud_data)
        combined_data["historical_data"] = self.historical_data

        # + MQTT
        for k, v in self.mqtt_data.items():
            combined_data[k] = v

        return combined_data

    def _fetch_all_quotas(self) -> dict:
        """Blocking call: GET /iot-open/sign/device/quota/all."""
        endpoint = f"{self.base_url}/iot-open/sign/device/quota/all"
        params = {"sn": self.device_sn}
        headers = self._generate_signature(params, method="GET", path="/iot-open/sign/device/quota/all")

        try:
            resp = requests.get(endpoint, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data_json = resp.json()
            return data_json.get("data", {})
        except Exception as exc:
            _LOGGER.error("Failed to fetch all quotas: %s", exc)
            return {}

    def _fetch_historical_data(self) -> dict:
        """
        Blocking call: POST /iot-open/sign/device/quota/data
        Zeitfenster hier exemplarisch (1 Woche).
        """
        endpoint = f"{self.base_url}/iot-open/sign/device/quota/data"
        payload = {
            "sn": self.device_sn,
            "params": {
                "code": "JT303_Dashboard_Overview_Summary_Week",
                "beginTime": "2024-06-17 00:00:00",
                "endTime": "2024-06-23 23:59:59"
            }
        }
        headers = self._generate_signature(payload, method="POST", path="/iot-open/sign/device/quota/data")
        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data_json = resp.json()
            return data_json.get("data", {})
        except Exception as exc:
            _LOGGER.error("Failed to fetch historical data: %s", exc)
            return {}

    def fetch_mqtt_certification(self) -> dict:
        """
        Blocking call: GET /iot-open/sign/certification
        to retrieve MQTT credentials.
        """
        endpoint = f"{self.base_url}/iot-open/sign/certification"
        payload = {}
        headers = self._generate_signature(payload, method="GET", path="/iot-open/sign/certification")
        try:
            response = requests.get(endpoint, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == "0":
                cert_info = data.get("data", {})
                self.mqtt_cert_data = cert_info
                _LOGGER.debug("Fetched MQTT cert data: %s", cert_info)
                return cert_info
            else:
                _LOGGER.error("MQTT certification request returned code %s: %s",
                              data.get("code"), data.get("message"))
        except Exception as exc:
            _LOGGER.error("Failed to fetch MQTT certification: %s", exc)
        return {}

    def _generate_signature(self, payload: dict, method: str, path: str) -> dict:
        """HMAC-SHA256 signature creation according to EcoFlow docs."""
        nonce = "123456"
        timestamp = str(int(time.time() * 1000))

        flatten_str = self._flatten_dict(payload)
        sign_base = flatten_str
        if sign_base:
            sign_base += "&"
        sign_base += f"accessKey={self.access_key}&nonce={nonce}&timestamp={timestamp}"

        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            sign_base.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "accessKey": self.access_key,
            "nonce": nonce,
            "timestamp": timestamp,
            "sign": signature,
        }
        if method == "POST":
            headers["Content-Type"] = "application/json;charset=UTF-8"

        return headers

    def _flatten_dict(self, data: dict, prefix: str = "") -> str:
        """Flatten nested dict/list for EcoFlow's sign method."""
        items = []
        if not data:
            return ""
        for key in sorted(data.keys()):
            val = data[key]
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(val, dict):
                items.append(self._flatten_dict(val, new_key))
            elif isinstance(val, list):
                for i, v in enumerate(val):
                    if isinstance(v, dict):
                        items.append(self._flatten_dict(v, f"{new_key}[{i}]"))
                    else:
                        items.append(f"{new_key}[{i}]={v}")
            else:
                items.append(f"{new_key}={val}")
        return "&".join(i for i in items if i)

    def update_mqtt_data(self, topic: str, payload: dict):
        """
        Called by MQTT handler when an MQTT message arrives.
        We store the data in self.mqtt_data, then push updated data to sensors.
        """
        _LOGGER.debug("MQTT message on %s: %s", topic, payload)
        for k, v in payload.items():
            self.mqtt_data[k] = v

        # Force an immediate update, so sensors see the new data
        if self.data is not None:
            combined_data = dict(self.data)
            for k, val in payload.items():
                combined_data[k] = val
            self.async_set_updated_data(combined_data)
        else:
            self.async_set_updated_data(self.data or {})

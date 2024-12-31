"""
coordinator.py – Coordinator for EcoFlow PowerOcean data (REST + MQTT),
with:
 - Potential 5-second or custom polling for normal "all quotas" data
 - Potential 5-minute or custom interval for historical data
 - Automatic fetch of MQTT certificate
 - Thread-safety fix: we do NOT call async_set_updated_data(...) directly from the MQTT thread
"""

import logging
import time
import hashlib
import hmac
import requests
from datetime import timedelta, datetime

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant, CALLBACK_TYPE

_LOGGER = logging.getLogger(__name__)

class EcoFlowDataCoordinator(DataUpdateCoordinator):
    """
    Coordinates data updates from EcoFlow Cloud + merges MQTT updates safely.

    - You can set update_interval=timedelta(seconds=5) for quick polling (or any interval).
    - We store normal cloud_data in self.cloud_data, historical in self.historical_data, and MQTT in self.mqtt_data.
    - Thread-safety fix: actual set_updated_data is scheduled via self.hass.add_job(...) in update_mqtt_data(...).
    """

    def __init__(self, hass: HomeAssistant, config_entry):
        super().__init__(
            hass,
            _LOGGER,
            name="EcoFlowDataCoordinator",
            update_interval=timedelta(seconds=5),  # Beispiel: alle 5 Sekunden
        )
        self._hass = hass
        self._config_entry = config_entry

        data = config_entry.data
        self.access_key = data.get("access_key")
        self.secret_key = data.get("secret_key")
        self.device_sn = data.get("device_sn")
        self.mqtt_enabled = data.get("mqtt_enabled", False)

        self.base_url = "https://api-e.ecoflow.com"

        # Local caches
        self.cloud_data = {}
        self.historical_data = {}
        self.mqtt_data = {}
        self.mqtt_cert_data = {}

        # Just an example if you want 5-minute history fetch logic:
        self._last_history_fetch = None
        self._history_interval_sec = 300  # 5 min

    async def _async_update_data(self):
        """
        Called by DataUpdateCoordinator each update_interval (5s here).
        Merge normal data + historical (maybe each 5 min) + MQTT.
        """
        try:
            self.cloud_data = await self._hass.async_add_executor_job(self._fetch_all_quotas)
        except Exception as exc:
            _LOGGER.error("Error fetching normal quotas: %s", exc)
            raise

        # Optional: fetch historical data every 5 min
        need_history = False
        now = datetime.now()
        if not self._last_history_fetch:
            need_history = True
        else:
            delta_sec = (now - self._last_history_fetch).total_seconds()
            if delta_sec > self._history_interval_sec:
                need_history = True

        if need_history:
            try:
                _LOGGER.debug("Fetching historical data ...")
                self.historical_data = await self._hass.async_add_executor_job(self._fetch_historical_data)
            except Exception as exc:
                _LOGGER.error("Error fetching historical data: %s", exc)
            self._last_history_fetch = now

        # Merge everything
        combined = {}
        combined.update(self.cloud_data)
        combined["historical_data"] = self.historical_data

        for k, v in self.mqtt_data.items():
            combined[k] = v

        return combined

    def _fetch_all_quotas(self) -> dict:
        """Blocking call: GET /iot-open/sign/device/quota/all."""
        endpoint = f"{self.base_url}/iot-open/sign/device/quota/all"
        params = {"sn": self.device_sn}
        headers = self._generate_signature(params, "GET", "/iot-open/sign/device/quota/all")

        try:
            r = requests.get(endpoint, params=params, headers=headers, timeout=10)
            r.raise_for_status()
            js = r.json()
            return js.get("data", {})
        except Exception as e:
            _LOGGER.error("Failed to fetch all quotas: %s", e)
            return {}

    def _fetch_historical_data(self) -> dict:
        """Blocking call: POST /iot-open/sign/device/quota/data for historical info."""
        endpoint = f"{self.base_url}/iot-open/sign/device/quota/data"
        payload = {
            "sn": self.device_sn,
            "params": {
                "code": "JT303_Dashboard_Overview_Summary_Week",
                "beginTime": "2024-06-17 00:00:00",
                "endTime": "2024-06-23 23:59:59"
            }
        }
        headers = self._generate_signature(payload, "POST", "/iot-open/sign/device/quota/data")
        try:
            r = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            r.raise_for_status()
            js = r.json()
            return js.get("data", {})
        except Exception as e:
            _LOGGER.error("Failed to fetch historical data: %s", e)
            return {}

    def fetch_mqtt_certification(self) -> dict:
        """Blocking call: GET /iot-open/sign/certification for MQTT credentials."""
        endpoint = f"{self.base_url}/iot-open/sign/certification"
        payload = {}
        headers = self._generate_signature(payload, "GET", "/iot-open/sign/certification")

        try:
            r = requests.get(endpoint, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get("code") == "0":
                self.mqtt_cert_data = data.get("data", {})
                _LOGGER.debug("Fetched MQTT cert data: %s", self.mqtt_cert_data)
                return self.mqtt_cert_data
            else:
                _LOGGER.error("MQTT cert request code %s: %s",
                              data.get("code"), data.get("message"))
        except Exception as e:
            _LOGGER.error("Failed to fetch MQTT certification: %s", e)
        return {}

    def update_mqtt_data(self, topic: str, payload: dict):
        """
        Called from the Paho MQTT thread in mqtt_handler.py -> on_message.
        We must not call async_set_updated_data(...) here directly.
        Instead, schedule an async call in the HA event loop.
        """
        _LOGGER.debug("MQTT message on %s: %s", topic, payload)
        for k, v in payload.items():
            self.mqtt_data[k] = v

        if self.data is not None:
            combined_data = dict(self.data)
            for k, val in payload.items():
                combined_data[k] = val

            # schedule the actual update in the event loop
            self.hass.add_job(self._async_update_mqtt_data, combined_data)
        else:
            self.hass.add_job(self._async_update_mqtt_data, self.data or {})

    async def _async_update_mqtt_data(self, new_data: dict):
        """
        Runs in HA's event loop to safely call async_set_updated_data.
        This avoids the "thread other than the event loop" error.
        """
        self.async_set_updated_data(new_data)

    def _generate_signature(self, payload: dict, method: str, path: str) -> dict:
        """Creates HMAC-SHA256 signature per EcoFlow docs."""
        nonce = "123456"
        ts = str(int(time.time() * 1000))

        flat = self._flatten_dict(payload)
        sign_base = flat
        if sign_base:
            sign_base += "&"
        sign_base += f"accessKey={self.access_key}&nonce={nonce}&timestamp={ts}"

        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            sign_base.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "accessKey": self.access_key,
            "nonce": nonce,
            "timestamp": ts,
            "sign": signature,
        }
        if method == "POST":
            headers["Content-Type"] = "application/json;charset=UTF-8"

        return headers

    def _flatten_dict(self, data: dict, prefix: str = "") -> str:
        """Flatten dict for EcoFlow's sign method (ASCII-sorted, handle arrays)."""
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

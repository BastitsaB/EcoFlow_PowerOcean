"""
coordinator.py – Coordinator for EcoFlow PowerOcean data (REST + MQTT),
including automatic fetch of MQTT certificate from /iot-open/sign/certification.
"""

import logging
import time
import hashlib
import hmac
import requests

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class EcoFlowDataCoordinator(DataUpdateCoordinator):
    """
    Coordinates data updates from EcoFlow Cloud + merges MQTT updates.
    Also capable of fetching MQTT certificate info if mqtt_enabled is True.
    """

    def __init__(self, hass: HomeAssistant, config_entry):
        """
        :param hass: HomeAssistant instance
        :param config_entry: ConfigEntry with access_key, secret_key, device_sn, etc.
        """
        super().__init__(
            hass,
            _LOGGER,
            name="EcoFlowDataCoordinator",
            update_interval=None  # We'll call updates manually or schedule them
        )
        self._hass = hass
        self._config_entry = config_entry

        data = config_entry.data
        self.access_key = data.get("access_key")
        self.secret_key = data.get("secret_key")
        self.device_sn = data.get("device_sn")
        self.mqtt_enabled = data.get("mqtt_enabled", False)

        self.base_url = "https://api-e.ecoflow.com"

        # Separate "local caches"
        self.cloud_data = {}        # for "all quotas" etc.
        self.historical_data = {}   # e.g. timespan data
        self.mqtt_data = {}         # data merged from MQTT
        self.mqtt_cert_data = {}    # certificate info from /iot-open/sign/certification

    async def _async_update_data(self):
        """
        Called by DataUpdateCoordinator to refresh data.
        Return a dict that gets stored in self.data.
        """
        try:
            # 1) Get "all quotas"
            self.cloud_data = await self._hass.async_add_executor_job(self._fetch_all_quotas)
            # 2) Get historical data
            self.historical_data = await self._hass.async_add_executor_job(self._fetch_historical_data)
        except Exception as exc:
            _LOGGER.error("Error fetching data from EcoFlow Cloud: %s", exc)
            raise

        # Merge everything into one dictionary
        combined_data = {}

        # 1) cloud_data
        combined_data.update(self.cloud_data)
        # 2) historical_data as a sub-key
        combined_data["historical_data"] = self.historical_data
        # 3) MQTT data
        for k, v in self.mqtt_data.items():
            combined_data[k] = v

        return combined_data

    def _fetch_all_quotas(self) -> dict:
        """Blocking call to fetch /iot-open/sign/device/quota/all for current data."""
        endpoint = f"{self.base_url}/iot-open/sign/device/quota/all"
        params = {"sn": self.device_sn}
        headers = self._generate_signature(params, method="GET", path="/iot-open/sign/device/quota/all")

        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            resp_json = response.json()
            return resp_json.get("data", {})
        except Exception as exc:
            _LOGGER.error("Failed to fetch all quotas: %s", exc)
            return {}

    def _fetch_historical_data(self) -> dict:
        """
        Example for a timespan-based request (1 week).
        POST /iot-open/sign/device/quota/data
        Adjust the date range as needed.
        """
        endpoint = f"{self.base_url}/iot-open/sign/device/quota/data"
        payload = {
            "sn": self.device_sn,
            "params": {
                "code": "JT303_Dashboard_Overview_Summary_Week",
                "beginTime": "2024-06-17 00:00:00",
                "endTime":   "2024-06-23 23:59:59"
            }
        }
        headers = self._generate_signature(payload, method="POST", path="/iot-open/sign/device/quota/data")
        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            resp = response.json()
            return resp.get("data", {})
        except Exception as exc:
            _LOGGER.error("Failed to fetch historical data: %s", exc)
            return {}

    def fetch_mqtt_certification(self) -> dict:
        """
        Blocking call: GET /iot-open/sign/certification
        to retrieve MQTT credentials for (certificateAccount, certificatePassword, url, port, protocol).
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
        """Creates the HMAC-SHA256 signature for EcoFlow's sign-based endpoints."""
        nonce = "123456"
        timestamp = str(int(time.time() * 1000))

        flat_str = self._flatten_dict(payload)
        sign_base = flat_str
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
        """Flatten nested dict/list for EcoFlow ASCII-sorted sign string."""
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
        Called by the MQTT handler whenever a relevant message arrives.
        We store the data in self.mqtt_data, then call self.async_set_updated_data(...)
        to re-publish new data to sensors.
        """
        _LOGGER.debug("MQTT message on %s: %s", topic, payload)
        for k, v in payload.items():
            self.mqtt_data[k] = v

        # Force an immediate update, so sensors see the new data
        if self.data is not None:
            # self.data is the last state from _async_update_data
            combined_data = dict(self.data)  # copy
            # Merge new MQTT info
            for k, val in payload.items():
                combined_data[k] = val
            self.async_set_updated_data(combined_data)
        else:
            # If for some reason self.data not set yet, just do a normal coordinator refresh
            self.async_set_updated_data(self.data or {})

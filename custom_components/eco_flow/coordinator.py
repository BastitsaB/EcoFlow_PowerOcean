"""
coordinator.py – Coordinator for EcoFlow PowerOcean data (REST + MQTT).
Now with automatic fetch of MQTT certification (/iot-open/sign/certification).
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
    Also automatically fetches MQTT certificate info if needed.
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
            update_interval=None  # We'll trigger manual or scheduled updates ourselves
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
        self.cloud_data = {}       # "All Quotas" or other REST data
        self.historical_data = {}  # e.g. timespan data
        self.mqtt_data = {}        # Merged data from MQTT messages
        self.mqtt_cert_data = {}   # Holds certificate info from /iot-open/sign/certification

    async def _async_update_data(self):
        """
        Called by the coordinator to refresh data. 
        We can fetch "all quotas" and historical data here.
        """
        try:
            self.cloud_data = await self.hass.async_add_executor_job(self._fetch_all_quotas)
            self.historical_data = await self.hass.async_add_executor_job(self._fetch_historical_data)
        except Exception as exc:
            _LOGGER.error("Error fetching data from EcoFlow Cloud: %s", exc)
            raise

        # Merge everything in one dict, also include MQTT data
        combined_data = {}
        combined_data.update(self.cloud_data)  # e.g. all quotas
        combined_data["historical_data"] = self.historical_data

        # Merge MQTT updates
        for k, v in self.mqtt_data.items():
            combined_data[k] = v

        return combined_data

    def _fetch_all_quotas(self) -> dict:
        """Blocking call to fetch the 'all quotas' (current data) from EcoFlow Cloud."""
        endpoint = f"{self.base_url}/iot-open/sign/device/quota/all"
        params = {"sn": self.device_sn}
        headers = self._generate_signature(params, method="GET", path="/iot-open/sign/device/quota/all")
        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            resp = response.json()
            return resp.get("data", {})
        except Exception as exc:
            _LOGGER.error("Failed to fetch all quotas: %s", exc)
            return {}

    def _fetch_historical_data(self) -> dict:
        """
        Example for a timespan-based request (1 week).
        POST /iot-open/sign/device/quota/data
        """
        endpoint = f"{self.base_url}/iot-open/sign/device/quota/data"
        payload = {
            "sn": self.device_sn,
            "params": {
                "code": "JT303_Dashboard_Overview_Summary_Week",
                # Demo time window – adapt as needed
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
        to retrieve MQTT credentials (certificateAccount, certificatePassword, etc.).
        """
        endpoint = f"{self.base_url}/iot-open/sign/certification"
        # Typically no query parameters, just sign an empty payload or adapt if needed
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
        """Create HMAC-SHA256 signature according to EcoFlow docs."""
        import hashlib
        import hmac

        nonce = "123456"  # You could randomize or time-based
        import time
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
        """Flatten nested dict according to EcoFlow's ASCII sorting and array handling."""
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
        Called by MQTT handler whenever a relevant message arrives.
        Merge or store that data in self.mqtt_data and schedule an update.
        """
        _LOGGER.debug("MQTT message on %s: %s", topic, payload)
        for k, v in payload.items():
            self.mqtt_data[k] = v

        # Force an immediate coordinator update so sensors reflect new data
        self.async_set_updated_data(self.data)

    @property
    def data(self) -> dict:
        """
        The DataUpdateCoordinator stores the last _async_update_data() result
        in self.data. We also want to allow forced merges with MQTT.
        """
        # self.data is a property from DataUpdateCoordinator; 
        # but here, we can override or do additional merges if needed.
        # We'll just call super() to retrieve the internal _data.
        return super().data

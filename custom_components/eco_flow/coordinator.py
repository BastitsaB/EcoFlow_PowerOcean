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
    def __init__(self, hass: HomeAssistant, config_entry):
        super().__init__(
            hass,
            _LOGGER,
            name="EcoFlowDataCoordinator",
            update_interval=timedelta(seconds=180),
        )
        self._hass = hass
        self._config_entry = config_entry

        data = config_entry.data
        self.access_key = data.get("access_key")
        self.secret_key = data.get("secret_key")
        self.device_sn = data.get("device_sn")
        self.mqtt_enabled = data.get("mqtt_enabled", False)

        self.base_url = "https://api-e.ecoflow.com"

        self.cloud_data = {}
        self.historical_data = {}
        self.mqtt_data = {}
        self.mqtt_cert_data = {}

        self._last_history_fetch = None
        self._history_interval_sec = 3600

    def _unflatten_dict(self, data: dict, sep: str = ".") -> dict:
        """Reconstructs a nested dictionary from flattened keys."""
        result = {}
        for key, value in data.items():
            parts = key.split(sep)
            d = result
            for part in parts[:-1]:
                if part not in d:
                    d[part] = {}
                d = d[part]
            d[parts[-1]] = value
        return result

    async def _async_update_data(self):
        try:
            raw_data = await self._hass.async_add_executor_job(self._fetch_all_quotas)
            self.cloud_data = self._unflatten_dict(raw_data)

            if self._should_fetch_history():
                history = await self._hass.async_add_executor_job(self._fetch_historical_data)
                self.historical_data = history

            combined = dict(self.cloud_data)
            combined.update(self.historical_data)
            combined.update(self.mqtt_data)

            _LOGGER.debug("Kombinierte Daten: %s", combined)
            return combined
        except Exception as exc:
            _LOGGER.error("Fehler beim Aktualisieren der Daten: %s", exc)
            raise

    def _should_fetch_history(self) -> bool:
        now = datetime.now()
        if not self._last_history_fetch or (now - self._last_history_fetch).total_seconds() > self._history_interval_sec:
            self._last_history_fetch = now
            return True
        return False

    def _fetch_all_quotas(self) -> dict:
        endpoint = f"{self.base_url}/iot-open/sign/device/quota/all"
        params = {"sn": self.device_sn}
        headers = self._generate_signature(params, "GET", "/iot-open/sign/device/quota/all")

        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            js = response.json()
            _LOGGER.debug("Abruf aller Quotas: %s", js.get("data", {}))
            return js.get("data", {})
        except Exception as e:
            _LOGGER.error("Fehler beim Abrufen aller Quotas: %s", e)
            return {}

    def _fetch_historical_data(self) -> dict:
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
            response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            js = response.json()
            _LOGGER.debug("Abruf historischer Daten: %s", js.get("data", {}))
            return js.get("data", {})
        except Exception as e:
            _LOGGER.error("Fehler beim Abrufen historischer Daten: %s", e)
            return {}

    def update_mqtt_data(self, topic: str, payload: dict):
        _LOGGER.debug("MQTT-Nachricht auf %s: %s", topic, payload)
        flat_data = self._flatten_dict(payload)
        for key, value in flat_data.items():
            if key not in self.cloud_data:
                self.mqtt_data[key] = value
            else:
                _LOGGER.warning("MQTT-Daten ignoriert: Schlüssel %s existiert bereits in cloud_data", key)
        if self.data is not None:
            combined_data = dict(self.data)
            combined_data.update(self.mqtt_data)
            self.hass.add_job(self._async_update_mqtt_data, combined_data)
        else:
            self.hass.add_job(self._async_update_mqtt_data, self.data or {})

    async def _async_update_mqtt_data(self, new_data: dict):
        self.async_set_updated_data(new_data)

    def _generate_signature(self, payload: dict, method: str, path: str) -> dict:
        nonce = "123456"
        ts = str(int(time.time() * 1000))

        flat = self._flatten_dict(payload)
        if flat:
            sign_base = "&".join(f"{k}={v}" for k, v in sorted(flat.items()))
            sign_base += "&"
        else:
            sign_base = ""
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

    def _flatten_dict(self, data: dict, parent_key: str = "", sep: str = ".") -> dict:
        items = {}
        for k, v in data.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten_dict(v, new_key, sep=sep))
            elif isinstance(v, list):
                for idx, item in enumerate(v):
                    if isinstance(item, dict):
                        items.update(self._flatten_dict(item, f"{new_key}[{idx}]", sep=sep))
                    else:
                        items[f"{new_key}[{idx}]"] = item
            else:
                items[new_key] = v
        return items
    
    def fetch_mqtt_certification(self) -> dict:
        """
        Fetch the MQTT certification required for the connection.
        """
        endpoint = f"{self.base_url}/iot-open/sign/certification"
        payload = {}
        headers = self._generate_signature(payload, "GET", "/iot-open/sign/certification")

        try:
            response = requests.get(endpoint, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == "0":
                self.mqtt_cert_data = data.get("data", {})
                _LOGGER.debug("MQTT certification fetched: %s", self.mqtt_cert_data)
                return self.mqtt_cert_data
            else:
                _LOGGER.error(
                    "Error fetching MQTT certification: Code %s, Message %s",
                    data.get("code"),
                    data.get("message"),
                )
        except Exception as e:
            _LOGGER.error("Exception while fetching MQTT certification: %s", e)
        return {}


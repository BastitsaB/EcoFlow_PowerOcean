"""
coordinator.py – Coordinator for EcoFlow PowerOcean data (REST + MQTT),
mit:
 - 180-Sekunden-Polling für normale "all quotas" Daten
 - 60-Minuten-Polling für historische Daten
 - Automatisches Abrufen des MQTT-Zertifikats bei Bedarf
 - Thread-Safety-Fix: async_set_updated_data wird sicher im HA-Event-Loop ausgeführt
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
    Koordiniert Datenaktualisierungen von EcoFlow Cloud und integriert MQTT-Daten sicher.

    - Polling für normale (aktuelle) Daten alle 180 Sekunden
    - Historische Daten nur alle 5 Minuten
    """

    def __init__(self, hass: HomeAssistant, config_entry):
        super().__init__(
            hass,
            _LOGGER,
            name="EcoFlowDataCoordinator",
            update_interval=timedelta(seconds=180),  # Polling alle 180 Sekunden
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
        self.cloud_data = {}
        self.historical_data = {}
        self.mqtt_data = {}
        self.mqtt_cert_data = {}

        # Historische Daten-Abfrage-Intervall
        self._last_history_fetch = None
        self._history_interval_sec = 3600  # 1 Stunde

    async def _async_update_data(self):
        try:
            # Abruf der normalen Quotas
            self.cloud_data = await self._hass.async_add_executor_job(self._fetch_all_quotas)
        except Exception as exc:
            _LOGGER.error("Fehler beim Abrufen der normalen Quotas: %s", exc)
            raise

        # Historische Daten
        need_history = False
        now = datetime.now()
        if not self._last_history_fetch or (now - self._last_history_fetch).total_seconds() > self._history_interval_sec:
            need_history = True

        if need_history:
            try:
                self.historical_data = await self._hass.async_add_executor_job(self._fetch_historical_data)
            except Exception as exc:
                _LOGGER.error("Fehler beim Abrufen historischer Daten: %s", exc)
            self._last_history_fetch = now

        # Kombinierte Datenstruktur erstellen
        combined = dict(self.cloud_data)  # Basisdaten
        combined.update(self.historical_data)  # Historische Daten hinzufügen
        for key, value in self.mqtt_data.items():
            combined[key] = value  # MQTT-Daten hinzufügen oder aktualisieren

        _LOGGER.debug("Kombinierte Daten: %s", combined)
        return combined

def _process_get_all_quota_response(self, data: dict) -> dict:
    """Prozessiert und validiert die Quotas-Daten."""
    try:
        processed_data = self._flatten_dict(data)
        _LOGGER.debug("Prozessierte Quotas-Daten: %s", processed_data)
        return processed_data
    except Exception as e:
        _LOGGER.error("Fehler bei der Verarbeitung der Quotas-Daten: %s", e)
        return {}


def _fetch_all_quotas(self) -> dict:
    """Blockierender Aufruf: GET /iot-open/sign/device/quota/all."""
    endpoint = f"{self.base_url}/iot-open/sign/device/quota/all"
    params = {"sn": self.device_sn}
    headers = self._generate_signature(params, "GET", "/iot-open/sign/device/quota/all")

    try:
        r = requests.get(endpoint, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        js = r.json()
        _LOGGER.debug("Abruf aller Quotas: %s", js.get("data", {}))
        raw_data = js.get("data", {})
        return self._process_get_all_quota_response(raw_data)
    except Exception as e:
        _LOGGER.error("Fehler beim Abrufen aller Quotas: %s", e)
        return {}


    def _fetch_historical_data(self) -> dict:
        """Blockierender Aufruf: POST /iot-open/sign/device/quota/data für historische Informationen."""
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
            _LOGGER.debug("Abruf historischer Daten: %s", js.get("data", {}))
            return js.get("data", {})
        except Exception as e:
            _LOGGER.error("Fehler beim Abrufen historischer Daten: %s", e)
            return {}

    def fetch_mqtt_certification(self) -> dict:
        """Blockierender Aufruf: GET /iot-open/sign/certification für MQTT-Zugangsdaten."""
        endpoint = f"{self.base_url}/iot-open/sign/certification"
        payload = {}
        headers = self._generate_signature(payload, "GET", "/iot-open/sign/device/quota/all")

        try:
            r = requests.get(endpoint, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get("code") == "0":
                self.mqtt_cert_data = data.get("data", {})
                _LOGGER.debug("MQTT-Zertifikatsdaten abgerufen: %s", self.mqtt_cert_data)
                return self.mqtt_cert_data
            else:
                _LOGGER.error("MQTT-Zertifikatsanfrage-Code %s: %s",
                              data.get("code"), data.get("message"))
        except Exception as e:
            _LOGGER.error("Fehler beim Abrufen des MQTT-Zertifikats: %s", e)
        return {}

    def update_mqtt_data(self, topic: str, payload: dict):
        """
        Verarbeitung und Integration von MQTT-Daten.
        """
        _LOGGER.debug("MQTT-Nachricht auf %s: %s", topic, payload)
        
        # Daten flach darstellen
        flat_data = self._flatten_dict(payload)

        # Update mqtt_data
        for key, value in flat_data.items():
            if key not in self.cloud_data:  # Überschreiben von cloud_data vermeiden
                self.mqtt_data[key] = value
            else:
                _LOGGER.warning("MQTT-Daten ignoriert: Schlüssel %s existiert bereits in cloud_data", key)

        # Daten im Event-Loop aktualisieren
        if self.data is not None:
            combined_data = dict(self.data)
            combined_data.update(self.mqtt_data)
            self.hass.add_job(self._async_update_mqtt_data, combined_data)
        else:
            self.hass.add_job(self._async_update_mqtt_data, self.data or {})

    async def _async_update_mqtt_data(self, new_data: dict):
        """
        Führt async_set_updated_data sicher im HA-Event-Loop aus.
        """
        self.async_set_updated_data(new_data)

    def _generate_signature(self, payload: dict, method: str, path: str) -> dict:
        """Erstellt HMAC-SHA256 Signatur gemäß EcoFlow-Dokumentation."""
        nonce = "123456"
        ts = str(int(time.time() * 1000))

        flat = self._flatten_dict(payload)
        if flat:
            # Sortiere die Schlüssel und erstelle ein sign_base String
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
        """
        Flattet ein verschachteltes Dictionary in ein flaches Dictionary.
        Beispiel:
            {'a': {'b': 1}} -> {'a.b': 1}
            {'a': [ {'b': 1}, {'c': 2} ]} -> {'a[0].b':1, 'a[1].c':2}
        """
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

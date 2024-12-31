"""Sensor platform for EcoFlow PowerOcean (Cloud API with signature)."""

import logging
import time
import hashlib
import hmac
import requests
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import POWER_WATT
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up EcoFlow PowerOcean sensor entities."""
    coordinator = EcoFlowDataCoordinator(hass, config_entry)
    await coordinator.async_update_data()
    # Du kannst mehrere Entities hinzufügen, z.B. für Phase A, B, C usw.
    async_add_entities([
        EcoFlowPhaseSensor(coordinator, phase="A"),
        EcoFlowPhaseSensor(coordinator, phase="B"),
        EcoFlowPhaseSensor(coordinator, phase="C"),
        EcoFlowGenericSensor(coordinator, "bpSoc", "Battery SoC", "%"),
        EcoFlowGenericSensor(coordinator, "bpPwr", "Battery Power", POWER_WATT),
        EcoFlowGenericSensor(coordinator, "mpptPwr", "PV Power", POWER_WATT),
        # usw. – liste hier alle relevanten Sensoren auf
    ], True)

class EcoFlowDataCoordinator:
    """Coordinate data updates from EcoFlow Cloud (signed requests)."""

    def __init__(self, hass, config_entry):
        """Initialize with config data."""
        self._hass = hass
        self._config_entry = config_entry
        self._data = {}
        # Hier Access-/Secret-Key & SN (Geräte-ID) laden
        self._access_key = config_entry.data.get("access_key")
        self._secret_key = config_entry.data.get("secret_key")
        self._device_sn = config_entry.data.get("device_sn")

        # Basis-URL der EcoFlow API
        self._base_url = "https://api-e.ecoflow.com"

    async def async_update_data(self):
        """Fetch data from EcoFlow using signed requests."""
        try:
            # 1) Quotas mit GET /device/quota/all?sn=XXX
            #    Hier bekommst du schon sehr viele Felder zurück
            self._data = await self._hass.async_add_executor_job(
                self._fetch_all_quotas
            )
        except Exception as exc:
            _LOGGER.error("Error updating EcoFlow data: %s", exc)

    def _fetch_all_quotas(self) -> dict:
        """Blocking call to fetch all quotas from EcoFlow Cloud."""
        endpoint = f"{self._base_url}/iot-open/sign/device/quota/all"
        # Query-String = ?sn=DEIN_SN
        params = {"sn": self._device_sn}
        headers = self._generate_signature(params, method="GET", path="/iot-open/sign/device/quota/all")
        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json().get("data", {})
        except Exception as exc:
            _LOGGER.error("Error fetching EcoFlow data (all quotas): %s", exc)
            return {}

    def _generate_signature(self, payload: dict, method: str, path: str) -> dict:
        """
        Build the signature according to the EcoFlow docs.
        Steps:
          1. Flatten the payload in ASCII order
          2. Append accessKey, nonce, timestamp
          3. HMAC-SHA256 with secretKey
          4. Hex-encode
          5. Return HTTP headers with sign, nonce, timestamp, accessKey
        """
        # 1) Generate or use random nonce (z.B. 6-stellig)
        nonce = "123456"
        # 2) Current timestamp (UTC) in ms
        timestamp = str(int(time.time() * 1000))

        # Flatten query/body into key=value pairs in ASCII order
        flatten_str = self._flatten_dict(payload)

        # Step 3: add the extra keys
        # E.g. flatten_str += f"&accessKey={...}&nonce=...&timestamp=..."
        # Beachte: Falls du GET machst, sind 'payload' = query params
        # Bei POST steckts in body, dann evtl. kein params=? an der URL
        sign_base = flatten_str
        if sign_base:
            sign_base += "&"
        sign_base += f"accessKey={self._access_key}&nonce={nonce}&timestamp={timestamp}"

        # 4) HMAC-SHA256 sign
        signature = hmac.new(
            self._secret_key.encode("utf-8"),
            sign_base.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        # 5) Return necessary headers
        headers = {
            "accessKey": self._access_key,
            "nonce": nonce,
            "timestamp": timestamp,
            "sign": signature,
            # Je nach Endpunkt ggf. "Content-Type": "application/json;charset=UTF-8"
        }
        if method == "POST":
            headers["Content-Type"] = "application/json;charset=UTF-8"

        _LOGGER.debug("Signature base string: %s", sign_base)
        _LOGGER.debug("Generated signature: %s", signature)
        return headers

    def _flatten_dict(self, data: dict, prefix: str = "") -> str:
        """
        Recursively flatten nested dicts/arrays into the format required by EcoFlow:
        e.g.  "params.cmdSet=11&params.id=24&sn=123456789"
        Arrays: arrayName[0]=val0&arrayName[1]=val1
        """
        items = []
        if not data:
            return ""
        for key in sorted(data.keys()):
            val = data[key]
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(val, dict):
                # recursively flatten
                items.append(self._flatten_dict(val, new_key))
            elif isinstance(val, list):
                # convert list to arrayName[0]=val ...
                for i, v in enumerate(val):
                    if isinstance(v, dict):
                        # nested object in array
                        items.append(self._flatten_dict(v, f"{new_key}[{i}]"))
                    else:
                        items.append(f"{new_key}[{i}]={v}")
            else:
                items.append(f"{new_key}={val}")
        return "&".join(i for i in items if i)

    @property
    def data(self) -> dict:
        """Return the latest data from the device."""
        return self._data


# Beispiel-Entity für Phasen-Daten
class EcoFlowPhaseSensor(SensorEntity):
    """Representation of phase-based sensor (A, B, C)."""

    def __init__(self, coordinator: EcoFlowDataCoordinator, phase: str):
        """Initialize the sensor entity."""
        self._coordinator = coordinator
        self._phase = phase
        self._attr_name = f"EcoFlow PowerOcean Phase {phase}"
        self._attr_native_unit_of_measurement = POWER_WATT
        self._state = None

    @property
    def state(self):
        """Return the state of the sensor."""
        # Example: data might have "pcsAPhase", "pcsBPhase", "pcsCPhase"
        root_key = f"pcs{self._phase}Phase"
        phase_data = self._coordinator.data.get(root_key, {})
        # e.g. actPwr = -810.62787
        return phase_data.get("actPwr", 0)

    async def async_update(self):
        """Request latest data from the coordinator."""
        await self._coordinator.async_update_data()


# Beispiel-Entity für generische Einzelwerte
class EcoFlowGenericSensor(SensorEntity):
    """Representation of a generic sensor for a single quota key."""

    def __init__(self, coordinator: EcoFlowDataCoordinator, quota_key: str, name: str, unit):
        """Initialize the sensor entity."""
        self._coordinator = coordinator
        self._quota_key = quota_key
        self._attr_name = f"EcoFlow {name}"
        self._attr_native_unit_of_measurement = unit
        self._state = None

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._coordinator.data.get(self._quota_key, 0)

    async def async_update(self):
        """Request latest data from the coordinator."""
        await self._coordinator.async_update_data()

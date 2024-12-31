"""Sensor platform for EcoFlow PowerOcean, split into 4 devices."""

import logging
import time
import hashlib
import hmac
import requests
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import POWER_WATT, TEMP_CELSIUS, PERCENTAGE
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up EcoFlow sensors, grouped into separate devices."""
    coordinator = EcoFlowDataCoordinator(hass, config_entry)
    await coordinator.async_update_data()

    # ---------------------------
    # 1) PowerOcean-Gerät
    # ---------------------------
    powerocean_entities = [
        # Beispiel: Phasen A/B/C
        EcoFlowPhaseSensor(coordinator, phase="A", device_type="PowerOcean"),
        EcoFlowPhaseSensor(coordinator, phase="B", device_type="PowerOcean"),
        EcoFlowPhaseSensor(coordinator, phase="C", device_type="PowerOcean"),

        # Battery
        EcoFlowGenericSensor(
            coordinator, 
            quota_key="bpSoc", 
            friendly_name="Battery SoC", 
            unit=PERCENTAGE,
            device_type="PowerOcean"
        ),
        EcoFlowGenericSensor(
            coordinator, 
            quota_key="bpPwr", 
            friendly_name="Battery Power", 
            unit=POWER_WATT,
            device_type="PowerOcean"
        ),

        # PV
        EcoFlowGenericSensor(
            coordinator,
            quota_key="mpptPwr",
            friendly_name="PV Power",
            unit=POWER_WATT,
            device_type="PowerOcean"
        ),
    ]

    # ---------------------------
    # 2) PowerHeat-Gerät
    # ---------------------------
    powerheat_entities = [
        EcoFlowNestedSensor(
            coordinator,
            root_key="sectorA",
            friendly_name="Sector A Temp",
            sub_key="tempCurr",
            unit=TEMP_CELSIUS,
            device_type="PowerHeat"
        ),
        EcoFlowNestedSensor(
            coordinator,
            root_key="sectorB",
            friendly_name="Sector B Temp",
            sub_key="tempCurr",
            unit=TEMP_CELSIUS,
            device_type="PowerHeat"
        ),
        EcoFlowNestedSensor(
            coordinator,
            root_key="sectorDhw",
            friendly_name="Hot Water Temp",
            sub_key="tempCurr",
            unit=TEMP_CELSIUS,
            device_type="PowerHeat"
        ),
        EcoFlowHeatPumpSensor(
            coordinator,
            root_key="hpMaster",
            friendly_name="Heat Pump Master",
            device_type="PowerHeat"
        ),
        # Error Code, falls der zum PowerHeat gehört
        EcoFlowErrorCodeSensor(
            coordinator, 
            root_key="emsErrCode", 
            friendly_name="EMS Error Code", 
            device_type="PowerHeat"
        ),
    ]

    # ---------------------------
    # 3) PowerGlow-Gerät
    # ---------------------------
    powerglow_entities = [
        EcoFlowHrEnergyStreamSensor(coordinator, device_type="PowerGlow"),
        # Hier weitere Sensoren, falls PowerGlow noch mehr Felder hat
    ]

    # ---------------------------
    # 4) PowerPulse-Gerät
    # ---------------------------
    powerpulse_entities = [
        EcoFlowGenericSensor(
            coordinator,
            quota_key="evPwr",
            friendly_name="EV Power",
            unit=POWER_WATT,
            device_type="PowerPulse"
        ),
        EcoFlowGenericSensor(
            coordinator,
            quota_key="chargingStatus",
            friendly_name="EV Charging Status",
            unit=None,
            device_type="PowerPulse"
        ),
        EcoFlowGenericSensor(
            coordinator,
            quota_key="errorCode", 
            friendly_name="EV Error Code",
            unit=None,
            device_type="PowerPulse"
        ),
        # Falls hier noch mehr Felder für PowerPulse existieren ...
    ]

    # -----------------------------------------
    # Alle Entities zusammen an HA übergeben
    # -----------------------------------------
    all_entities = (
        powerocean_entities
        + powerheat_entities
        + powerglow_entities
        + powerpulse_entities
    )
    async_add_entities(all_entities, True)


class EcoFlowDataCoordinator:
    """Coordinate data updates from EcoFlow Cloud (signed requests)."""

    def __init__(self, hass, config_entry):
        self._hass = hass
        self._config_entry = config_entry
        self._data = {}
        self._access_key = config_entry.data.get("access_key")
        self._secret_key = config_entry.data.get("secret_key")
        self._device_sn = config_entry.data.get("device_sn")
        self._base_url = "https://api-e.ecoflow.com"

    async def async_update_data(self):
        """Fetch data from EcoFlow using signed requests."""
        try:
            self._data = await self._hass.async_add_executor_job(self._fetch_all_quotas)
        except Exception as exc:
            _LOGGER.error("Error updating EcoFlow data: %s", exc)

    def _fetch_all_quotas(self) -> dict:
        """Blocking call to fetch all quotas (PowerOcean data)."""
        endpoint = f"{self._base_url}/iot-open/sign/device/quota/all"
        params = {"sn": self._device_sn}
        headers = self._generate_signature(params, method="GET", path="/iot-open/sign/device/quota/all")
        resp_json = {}
        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            resp_json = response.json()
        except Exception as exc:
            _LOGGER.error("Error fetching EcoFlow data (all quotas): %s", exc)
        return resp_json.get("data", {})

    def _generate_signature(self, payload: dict, method: str, path: str) -> dict:
        nonce = "123456"
        timestamp = str(int(time.time() * 1000))
        flatten_str = self._flatten_dict(payload)
        sign_base = flatten_str
        if sign_base:
            sign_base += "&"
        sign_base += f"accessKey={self._access_key}&nonce={nonce}&timestamp={timestamp}"
        signature = hmac.new(
            self._secret_key.encode("utf-8"),
            sign_base.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "accessKey": self._access_key,
            "nonce": nonce,
            "timestamp": timestamp,
            "sign": signature,
        }
        if method == "POST":
            headers["Content-Type"] = "application/json;charset=UTF-8"
        return headers

    def _flatten_dict(self, data: dict, prefix: str = "") -> str:
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

    @property
    def data(self):
        return self._data

    @property
    def device_sn(self):
        return self._device_sn


# ------------------------------------------------------------------------------------
# Gemeinsame Basisklasse, die je nach device_type unterschiedliche Geräte erstellt
# ------------------------------------------------------------------------------------

class EcoFlowBaseSensor(SensorEntity):
    """Gemeinsame Basisklasse, damit wir device_info & unique_id definieren."""
    def __init__(self, coordinator: EcoFlowDataCoordinator, device_type: str):
        """device_type z.B. 'PowerOcean', 'PowerHeat', 'PowerGlow', 'PowerPulse'."""
        self._coordinator = coordinator
        self._device_type = device_type  # Damit wir separate Geräte anlegen können

    @property
    def device_info(self):
        """
        Wir definieren ein eigenes Geräte-Objekt pro device_type.
        So tauchen in HA mehrere Geräte auf, obwohl wir denselben device_sn nutzen.
        """
        return {
            "identifiers": {(DOMAIN, self._coordinator.device_sn, self._device_type)},
            "name": f"EcoFlow {self._device_type}",
            "manufacturer": "EcoFlow",
            "model": self._device_type,
            "sw_version": "1.0.0",
        }


# ------------------------------------------------------------------------------------
# Sensor-Klassen mit device_type
# ------------------------------------------------------------------------------------

class EcoFlowPhaseSensor(EcoFlowBaseSensor):
    """Phase A/B/C für PowerOcean."""

    def __init__(self, coordinator, phase: str, device_type: str):
        super().__init__(coordinator, device_type)
        self._phase = phase
        self._attr_name = f"EcoFlow Phase {phase}"
        self._state = None

    @property
    def unique_id(self):
        # Nutze SN + device_type + phase
        return f"{self._coordinator.device_sn}_{self._device_type}_phase_{self._phase}"

    @property
    def native_unit_of_measurement(self):
        return POWER_WATT

    @property
    def state(self):
        root_key = f"pcs{self._phase}Phase"
        phase_data = self._coordinator.data.get(root_key, {})
        return phase_data.get("actPwr", 0)

    async def async_update(self):
        await self._coordinator.async_update_data()


class EcoFlowGenericSensor(EcoFlowBaseSensor):
    """Generischer Sensor für eine einzelne Kennzahl."""

    def __init__(self, coordinator, quota_key: str, friendly_name: str, unit, device_type: str):
        super().__init__(coordinator, device_type)
        self._quota_key = quota_key
        self._attr_name = f"EcoFlow {friendly_name}"
        self._unit = unit
        self._state = None

    @property
    def unique_id(self):
        return f"{self._coordinator.device_sn}_{self._device_type}_{self._quota_key}"

    @property
    def native_unit_of_measurement(self):
        return self._unit

    @property
    def state(self):
        return self._coordinator.data.get(self._quota_key, 0)

    async def async_update(self):
        await self._coordinator.async_update_data()


class EcoFlowNestedSensor(EcoFlowBaseSensor):
    """Sensor, der in data[root_key][sub_key] schaut."""

    def __init__(
        self, 
        coordinator, 
        root_key: str, 
        friendly_name: str, 
        sub_key: str, 
        unit: str, 
        device_type: str
    ):
        super().__init__(coordinator, device_type)
        self._root_key = root_key
        self._sub_key = sub_key
        self._attr_name = f"EcoFlow {friendly_name}"
        self._unit = unit

    @property
    def unique_id(self):
        return f"{self._coordinator.device_sn}_{self._device_type}_{self._root_key}_{self._sub_key}"

    @property
    def native_unit_of_measurement(self):
        return self._unit

    @property
    def state(self):
        root_obj = self._coordinator.data.get(self._root_key, {})
        return root_obj.get(self._sub_key, 0)

    async def async_update(self):
        await self._coordinator.async_update_data()


class EcoFlowHeatPumpSensor(EcoFlowBaseSensor):
    """Liests 'hpMaster' und gibt tempInlet als state + tempOutlet & tempAmbient als Attributes."""

    def __init__(self, coordinator, root_key: str, friendly_name: str, device_type: str):
        super().__init__(coordinator, device_type)
        self._root_key = root_key
        self._attr_name = f"EcoFlow {friendly_name}"

    @property
    def unique_id(self):
        return f"{self._coordinator.device_sn}_{self._device_type}_{self._root_key}"

    @property
    def native_unit_of_measurement(self):
        return TEMP_CELSIUS

    @property
    def state(self):
        root_obj = self._coordinator.data.get(self._root_key, {})
        return root_obj.get("tempInlet", 0)

    @property
    def extra_state_attributes(self):
        root_obj = self._coordinator.data.get(self._root_key, {})
        return {
            "tempOutlet": root_obj.get("tempOutlet"),
            "tempAmbient": root_obj.get("tempAmbient")
        }

    async def async_update(self):
        await self._coordinator.async_update_data()


class EcoFlowErrorCodeSensor(EcoFlowBaseSensor):
    """Liest z. B. 'emsErrCode': { 'errCode': [601] }."""

    def __init__(self, coordinator, root_key: str, friendly_name: str, device_type: str):
        super().__init__(coordinator, device_type)
        self._root_key = root_key
        self._attr_name = f"EcoFlow {friendly_name}"

    @property
    def unique_id(self):
        return f"{self._coordinator.device_sn}_{self._device_type}_{self._root_key}"

    @property
    def state(self):
        err_obj = self._coordinator.data.get(self._root_key, {})
        codes = err_obj.get("errCode", [])
        return codes[0] if codes else 0

    @property
    def extra_state_attributes(self):
        err_obj = self._coordinator.data.get(self._root_key, {})
        return {
            "all_error_codes": err_obj.get("errCode", [])
        }

    async def async_update(self):
        await self._coordinator.async_update_data()


class EcoFlowHrEnergyStreamSensor(EcoFlowBaseSensor):
    """PowerGlow: 'hrEnergyStream': [ { "temp": 22, "hrPwr": 0 } ]."""

    def __init__(self, coordinator, device_type: str):
        super().__init__(coordinator, device_type)
        self._attr_name = f"EcoFlow {device_type} HR Energy Stream"

    @property
    def unique_id(self):
        return f"{self._coordinator.device_sn}_{self._device_type}_hrEnergyStream"

    @property
    def native_unit_of_measurement(self):
        return POWER_WATT

    @property
    def state(self):
        arr = self._coordinator.data.get("hrEnergyStream", [])
        if len(arr) > 0:
            return arr[0].get("hrPwr", 0)
        return 0

    @property
    def extra_state_attributes(self):
        arr = self._coordinator.data.get("hrEnergyStream", [])
        if len(arr) > 0:
            return {"temp": arr[0].get("temp")}
        return {}

    async def async_update(self):
        await self._coordinator.async_update_data()

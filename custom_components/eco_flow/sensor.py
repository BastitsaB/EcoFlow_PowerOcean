"""
sensor.py – A comprehensive sensor setup for EcoFlow PowerOcean, 
covering nearly all documented fields from the EcoFlow API docs.
Comments in English, rest in Deutsch.
"""

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    POWER_WATT,
    ELECTRIC_CURRENT_AMPERE,
    ELECTRIC_POTENTIAL_VOLT,
    POWER_VOLT_AMPERE_REACTIVE,
    POWER_VOLT_AMPERE,
    PERCENTAGE,
    TEMP_CELSIUS
)
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """
    This function collects all sensor entities for EcoFlow:
    - System/Load/Grid/Battery
    - Phases (A/B/C) with vol, amp, actPwr, reactPwr, apparentPwr
    - MPPT data, Heat pump sectors, PowerGlow, PowerPulse
    - Historical data, etc.
    """
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensor_entities = []

    # 1) System / Battery / Grid
    sensor_entities.append(EcoFlowSingleValueSensor(coordinator, "sysLoadPwr", "System Load Power", POWER_WATT))
    sensor_entities.append(EcoFlowSingleValueSensor(coordinator, "sysGridPwr", "System Grid Power", POWER_WATT))
    sensor_entities.append(EcoFlowSingleValueSensor(coordinator, "bpSoc", "Battery SoC", PERCENTAGE))
    sensor_entities.append(EcoFlowSingleValueSensor(coordinator, "bpPwr", "Battery Power", POWER_WATT))
    sensor_entities.append(EcoFlowSingleValueSensor(coordinator, "mpptPwr", "PV Power", POWER_WATT))

    # 2) Phases A/B/C
    phase_letters = ["A", "B", "C"]
    phase_detail_keys = [
        ("vol", "Voltage", ELECTRIC_POTENTIAL_VOLT),
        ("amp", "Current", ELECTRIC_CURRENT_AMPERE),
        ("actPwr", "Active Power", POWER_WATT),
        ("reactPwr", "Reactive Power", POWER_VOLT_AMPERE_REACTIVE),
        ("apparentPwr", "Apparent Power", POWER_VOLT_AMPERE),
    ]
    for phase in phase_letters:
        for detail_key, detail_name, detail_unit in phase_detail_keys:
            sensor_entities.append(
                EcoFlowPhaseDetailSensor(
                    coordinator,
                    phase=phase,
                    detail_key=detail_key,
                    name_suffix=detail_name,
                    unit=detail_unit
                )
            )

    # 3) MPPT data (mpptHeartBeat -> mpptPv)
    for i in range(2):
        sensor_entities.append(EcoFlowMPPTSensor(coordinator, index=i))

    # 4) Heat Pump (sectorA, sectorB, sectorDhw, hpMaster)
    sensor_entities.append(EcoFlowNestedSensor(coordinator, "sectorA", "Sector A Temp", "tempCurr", TEMP_CELSIUS))
    sensor_entities.append(EcoFlowNestedSensor(coordinator, "sectorB", "Sector B Temp", "tempCurr", TEMP_CELSIUS))
    sensor_entities.append(EcoFlowNestedSensor(coordinator, "sectorDhw", "Hot Water Temp", "tempCurr", TEMP_CELSIUS))
    sensor_entities.append(EcoFlowHeatPumpSensor(coordinator, "hpMaster", "Heat Pump Master"))

    # 5) Error codes (emsErrCode)
    sensor_entities.append(EcoFlowErrorCodeSensor(coordinator, "emsErrCode", "EMS Error Code"))

    # 6) PowerGlow: hrEnergyStream
    sensor_entities.append(EcoFlowHrEnergyStreamSensor(coordinator, "PowerGlow HR Energy Stream"))

    # 7) PowerPulse: evPwr, chargingStatus, errorCode
    sensor_entities.append(EcoFlowSingleValueSensor(coordinator, "evPwr", "EV Power", POWER_WATT))
    sensor_entities.append(EcoFlowSingleValueSensor(coordinator, "chargingStatus", "EV Charging Status", None))
    sensor_entities.append(EcoFlowSingleValueSensor(coordinator, "errorCode", "EV Error Code", None))

    # 8) Historical Data
    sensor_entities.append(EcoFlowHistorySensor(coordinator, "Historical Data (Week)"))

    async_add_entities(sensor_entities)


# ------------------------------------------------------------------------------
# Base Sensor
# ------------------------------------------------------------------------------
class EcoFlowBaseSensor(SensorEntity):
    """
    Base class that relies on DataUpdateCoordinator for updates.
    We'll retrieve everything from coordinator.data.
    Comments in English.
    """

    def __init__(self, coordinator, sensor_name: str):
        self.coordinator = coordinator
        self._attr_name = sensor_name

    @property
    def device_info(self):
        """Group everything under one device or multiple if desired."""
        return {
            "identifiers": { (DOMAIN, self.coordinator.device_sn) },
            "name": "EcoFlow PowerOcean (All Data)",
            "manufacturer": "EcoFlow",
            "model": "PowerOcean",
            "model": "PowerOcean",
            "sw_version": "1.0.0",
        }

    @property
    def should_poll(self) -> bool:
        """No direct polling, we rely on coordinator."""
        return False

    async def async_update(self):
        """Request new data from the coordinator."""
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self):
        """Register update listener."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


# ------------------------------------------------------------------------------
# Generic Single-Value Sensor
# ------------------------------------------------------------------------------
class EcoFlowSingleValueSensor(EcoFlowBaseSensor):
    """Reads a single top-level key from coordinator.data."""

    def __init__(self, coordinator, key: str, friendly_name: str, unit):
        super().__init__(coordinator, friendly_name)
        self.key = key
        self._attr_native_unit_of_measurement = unit
        self._unique_id = f"{coordinator.device_sn}_{key}"
    def __init__(self, coordinator, key: str, friendly_name: str, unit):
        super().__init__(coordinator, friendly_name)
        self.key = key
        self._attr_native_unit_of_measurement = unit
        self._unique_id = f"{coordinator.device_sn}_{key}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        return self.coordinator.data.get(self.key, 0)


# ------------------------------------------------------------------------------
# Phase Detail Sensor (pcsAPhase, pcsBPhase, pcsCPhase)
# ------------------------------------------------------------------------------
class EcoFlowPhaseDetailSensor(EcoFlowBaseSensor):
    """
    Reads phase detail keys (vol, amp, actPwr, reactPwr, apparentPwr)
    from data["pcsAPhase"] / data["pcsBPhase"] / data["pcsCPhase"].
    """

    def __init__(self, coordinator, phase: str, detail_key: str, name_suffix: str, unit):
        super().__init__(coordinator, f"Phase {phase} {name_suffix}")
        self.phase = phase
        self.detail_key = detail_key
        self._attr_native_unit_of_measurement = unit
        self._unique_id = f"{coordinator.device_sn}_pcs{phase}Phase_{detail_key}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        root_key = f"pcs{self.phase}Phase"
        obj = self.coordinator.data.get(root_key, {})
        return obj.get(self.detail_key, 0)


# ------------------------------------------------------------------------------
# MPPT Sensor (mpptHeartBeat -> mpptPv)
# ------------------------------------------------------------------------------
class EcoFlowMPPTSensor(EcoFlowBaseSensor):
    """
    Example: data["mpptHeartBeat"] = [
      {
         "mpptPv": [
           { "vol": 0, "amp": 0.08, "pwr": 0 },
           { "vol": 26.25, "amp": 0, "pwr": 0 }
         ]
      }
    ]
    We index into mpptPv[index].
    """

    def __init__(self, coordinator, index: int):
        super().__init__(coordinator, f"MPPT PV[{index}]")
        self.index = index
        self._unique_id = f"{coordinator.device_sn}_mpptPv_{index}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def native_unit_of_measurement(self):
        return POWER_WATT

    @property
    def state(self):
        mppt_ary = self.coordinator.data.get("mpptHeartBeat", [])
        if len(mppt_ary) > 0:
            mpptPv_arr = mppt_ary[0].get("mpptPv", [])
            if self.index < len(mpptPv_arr):
                return mpptPv_arr[self.index].get("pwr", 0)
        return 0

    @property
    def extra_state_attributes(self):
        mppt_ary = self.coordinator.data.get("mpptHeartBeat", [])
        if len(mppt_ary) > 0:
            mpptPv_arr = mppt_ary[0].get("mpptPv", [])
            if self.index < len(mpptPv_arr):
                data = mpptPv_arr[self.index]
                return {
                    "vol": data.get("vol"),
                    "amp": data.get("amp")
                }
        return {}


# ------------------------------------------------------------------------------
# Nested Sensor (z. B. sectorA -> {"tempCurr": ...})
# ------------------------------------------------------------------------------
class EcoFlowNestedSensor(EcoFlowBaseSensor):
    """Reads data[root_key][sub_key]."""

    def __init__(self, coordinator, root_key: str, friendly_name: str, sub_key: str, unit):
        super().__init__(coordinator, friendly_name)
        self.root_key = root_key
        self.sub_key = sub_key
        self._attr_native_unit_of_measurement = unit
        self._unique_id = f"{coordinator.device_sn}_{root_key}_{sub_key}"

    @property
    def unique_id(self):
        return self._unique_id
        return self._unique_id

    @property
    def state(self):
        root_obj = self.coordinator.data.get(self.root_key, {})
        return root_obj.get(self.sub_key, 0)


# ------------------------------------------------------------------------------
# Heat Pump Sensor (hpMaster -> tempInlet, tempOutlet, tempAmbient)
# ------------------------------------------------------------------------------
class EcoFlowHeatPumpSensor(EcoFlowBaseSensor):
    """
    e.g. data["hpMaster"] = {
      "tempInlet": 22.5,
      "tempOutlet": 22.5,
      "tempAmbient": -3270
    }
    We'll show tempInlet as state, others as attributes.
    """

    def __init__(self, coordinator, root_key: str, friendly_name: str):
        super().__init__(coordinator, friendly_name)
        self.root_key = root_key
        self._unique_id = f"{coordinator.device_sn}_{root_key}"
    def __init__(self, coordinator, root_key: str, friendly_name: str):
        super().__init__(coordinator, friendly_name)
        self.root_key = root_key
        self._unique_id = f"{coordinator.device_sn}_{root_key}"

    @property
    def unique_id(self):
        return self._unique_id
        return self._unique_id

    @property
    def native_unit_of_measurement(self):
        return TEMP_CELSIUS

    @property
    def state(self):
        root_obj = self.coordinator.data.get(self.root_key, {})
        root_obj = self.coordinator.data.get(self.root_key, {})
        return root_obj.get("tempInlet", 0)

    @property
    def extra_state_attributes(self):
        root_obj = self.coordinator.data.get(self.root_key, {})
        root_obj = self.coordinator.data.get(self.root_key, {})
        return {
            "tempOutlet": root_obj.get("tempOutlet"),
            "tempAmbient": root_obj.get("tempAmbient")
        }


# ------------------------------------------------------------------------------
# ErrorCode Sensor (z. B. emsErrCode -> { "errCode": [601] })
# ------------------------------------------------------------------------------
class EcoFlowErrorCodeSensor(EcoFlowBaseSensor):
    """Reads an error code array from data[root_key]."""

    def __init__(self, coordinator, root_key: str, friendly_name: str):
        super().__init__(coordinator, friendly_name)
        self.root_key = root_key
        self._unique_id = f"{coordinator.device_sn}_{root_key}"
    def __init__(self, coordinator, root_key: str, friendly_name: str):
        super().__init__(coordinator, friendly_name)
        self.root_key = root_key
        self._unique_id = f"{coordinator.device_sn}_{root_key}"

    @property
    def unique_id(self):
        return self._unique_id
        return self._unique_id

    @property
    def state(self):
        err_obj = self.coordinator.data.get(self.root_key, {})
        err_obj = self.coordinator.data.get(self.root_key, {})
        codes = err_obj.get("errCode", [])
        return codes[0] if codes else 0

    @property
    def extra_state_attributes(self):
        err_obj = self.coordinator.data.get(self.root_key, {})
        err_obj = self.coordinator.data.get(self.root_key, {})
        return {
            "all_error_codes": err_obj.get("errCode", [])
        }


# ------------------------------------------------------------------------------
# PowerGlow HR Energy Stream (hrEnergyStream -> [ { "temp": 22, "hrPwr": 0 } ])
# ------------------------------------------------------------------------------
class EcoFlowHrEnergyStreamSensor(EcoFlowBaseSensor):
    """Displays 'hrPwr' as state and 'temp' as attribute."""

    def __init__(self, coordinator, friendly_name: str):
        super().__init__(coordinator, friendly_name)
        self._unique_id = f"{coordinator.device_sn}_hrEnergyStream"
    def __init__(self, coordinator, friendly_name: str):
        super().__init__(coordinator, friendly_name)
        self._unique_id = f"{coordinator.device_sn}_hrEnergyStream"

    @property
    def unique_id(self):
        return self._unique_id
        return self._unique_id

    @property
    def native_unit_of_measurement(self):
        return POWER_WATT

    @property
    def state(self):
        arr = self.coordinator.data.get("hrEnergyStream", [])
        arr = self.coordinator.data.get("hrEnergyStream", [])
        if len(arr) > 0:
            return arr[0].get("hrPwr", 0)
        return 0

    @property
    def extra_state_attributes(self):
        arr = self.coordinator.data.get("hrEnergyStream", [])
        arr = self.coordinator.data.get("hrEnergyStream", [])
        if len(arr) > 0:
            return {"temp": arr[0].get("temp")}
        return {}


# ------------------------------------------------------------------------------
# Historische Daten (z. B. "Self-sufficiency" im coordinator.data["historical_data"])
# ------------------------------------------------------------------------------
class EcoFlowHistorySensor(EcoFlowBaseSensor):
    """Displays 'Self-sufficiency' from data["historical_data"], entire block in attributes."""

    def __init__(self, coordinator, friendly_name: str):
        super().__init__(coordinator, friendly_name)
        self._unique_id = f"{coordinator.device_sn}_history"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        hist_data = self.coordinator.data.get("historical_data", {})
        data_arr = hist_data.get("data", [])
        for item in data_arr:
            if item.get("indexName") == "Self-sufficiency":
                return item.get("indexValue", 0)
        return 0

    @property
    def extra_state_attributes(self):
        hist_data = self.coordinator.data.get("historical_data", {})
        return {
            "raw_history_data": hist_data
        }

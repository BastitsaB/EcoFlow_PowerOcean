"""
sensor.py – A comprehensive sensor setup for EcoFlow PowerOcean, 
covering all documented fields from the EcoFlow API docs, 
each sensor is assigned to a different device (PowerOcean, PowerHeat, etc.).
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
    - PowerOcean-Gerät: Phasen (A/B/C), Battery, PV
    - PowerHeat-Gerät: sectors (sectorA, sectorB, sectorDhw), hpMaster
    - PowerGlow-Gerät: hrEnergyStream
    - PowerPulse-Gerät: evPwr, chargingStatus, errorCode
    - PowerHistory-Gerät: Historical Data
    
    So each group of sensors will appear under a separate "device" in HA.
    """
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    sensor_entities = []

    # --------------------------------------------------
    # 1) PowerOcean-Gerät
    #    Phasen A/B/C, Battery (bpSoc, bpPwr), PV (mpptPwr), sysLoadPwr, sysGridPwr
    # --------------------------------------------------
    # System
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="sysLoadPwr",
        friendly_name="System Load Power",
        unit=POWER_WATT,
        device_type="PowerOcean"
    ))
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="sysGridPwr",
        friendly_name="System Grid Power",
        unit=POWER_WATT,
        device_type="PowerOcean"
    ))
    # Battery
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="bpSoc",
        friendly_name="Battery SoC",
        unit=PERCENTAGE,
        device_type="PowerOcean"
    ))
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="bpPwr",
        friendly_name="Battery Power",
        unit=POWER_WATT,
        device_type="PowerOcean"
    ))
    # PV
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="mpptPwr",
        friendly_name="PV Power",
        unit=POWER_WATT,
        device_type="PowerOcean"
    ))

    # Phasen
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
            sensor_entities.append(EcoFlowPhaseDetailSensor(
                coordinator,
                phase=phase,
                detail_key=detail_key,
                name_suffix=detail_name,
                unit=detail_unit,
                device_type="PowerOcean"
            ))

    # --------------------------------------------------
    # 2) PowerHeat-Gerät
    #    Sektoren (A/B/Dhw) und hpMaster, plus ErrorCode (emsErrCode) wenn du es hier einsortieren willst
    # --------------------------------------------------
    sensor_entities.append(EcoFlowNestedSensor(
        coordinator,
        root_key="sectorA",
        friendly_name="Sector A Temp",
        sub_key="tempCurr",
        unit=TEMP_CELSIUS,
        device_type="PowerHeat"
    ))
    sensor_entities.append(EcoFlowNestedSensor(
        coordinator,
        root_key="sectorB",
        friendly_name="Sector B Temp",
        sub_key="tempCurr",
        unit=TEMP_CELSIUS,
        device_type="PowerHeat"
    ))
    sensor_entities.append(EcoFlowNestedSensor(
        coordinator,
        root_key="sectorDhw",
        friendly_name="Hot Water Temp",
        sub_key="tempCurr",
        unit=TEMP_CELSIUS,
        device_type="PowerHeat"
    ))
    sensor_entities.append(EcoFlowHeatPumpSensor(
        coordinator,
        root_key="hpMaster",
        friendly_name="Heat Pump Master",
        device_type="PowerHeat"
    ))
    # ErrorCode (emsErrCode) z. B. in "PowerHeat"
    sensor_entities.append(EcoFlowErrorCodeSensor(
        coordinator,
        root_key="emsErrCode",
        friendly_name="EMS Error Code",
        device_type="PowerHeat"
    ))

    # --------------------------------------------------
    # 3) PowerGlow-Gerät
    #    hrEnergyStream
    # --------------------------------------------------
    sensor_entities.append(EcoFlowHrEnergyStreamSensor(
        coordinator,
        friendly_name="PowerGlow HR Energy Stream",
        device_type="PowerGlow"
    ))

    # --------------------------------------------------
    # 4) PowerPulse-Gerät
    #    evPwr, chargingStatus, errorCode
    # --------------------------------------------------
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="evPwr",
        friendly_name="EV Power",
        unit=POWER_WATT,
        device_type="PowerPulse"
    ))
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="chargingStatus",
        friendly_name="EV Charging Status",
        unit=None,
        device_type="PowerPulse"
    ))
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="errorCode",
        friendly_name="EV Error Code",
        unit=None,
        device_type="PowerPulse"
    ))

    # --------------------------------------------------
    # 5) PowerHistory-Gerät
    #    Historische Daten
    # --------------------------------------------------
    sensor_entities.append(EcoFlowHistorySensor(
        coordinator,
        friendly_name="Historical Data (Week)",
        device_type="PowerHistory"
    ))

    async_add_entities(sensor_entities)


# ------------------------------------------------------------------------------
# Base Sensor (jetzt mit device_type)
# ------------------------------------------------------------------------------
class EcoFlowBaseSensor(SensorEntity):
    """
    Base class that uses device_type to separate sensors into multiple devices.
    """

    def __init__(self, coordinator, sensor_name: str, device_type: str):
        self.coordinator = coordinator
        self._attr_name = sensor_name
        self.device_type = device_type  # e.g. "PowerOcean", "PowerHeat", etc.

    @property
    def device_info(self):
        """
        Return a different device_info block per device_type,
        so each group of sensors appears under a separate device in HA.
        """
        return {
            "identifiers": {(DOMAIN, self.coordinator.device_sn, self.device_type)},
            "name": f"EcoFlow {self.device_type}",
            "manufacturer": "EcoFlow",
            "model": self.device_type,
            "sw_version": "1.0.0",
        }

    @property
    def should_poll(self) -> bool:
        return False

    async def async_update(self):
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self):
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


# ------------------------------------------------------------------------------
# EcoFlowSingleValueSensor
# ------------------------------------------------------------------------------
class EcoFlowSingleValueSensor(EcoFlowBaseSensor):
    """Reads a single top-level key (e.g. 'evPwr', 'errorCode')."""

    def __init__(self, coordinator, key: str, friendly_name: str, unit, device_type: str):
        super().__init__(coordinator, friendly_name, device_type)
        self.key = key
        self._attr_native_unit_of_measurement = unit
        self._unique_id = f"{coordinator.device_sn}_{device_type}_{key}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        return self.coordinator.data.get(self.key, 0)


# ------------------------------------------------------------------------------
# EcoFlowPhaseDetailSensor
# ------------------------------------------------------------------------------
class EcoFlowPhaseDetailSensor(EcoFlowBaseSensor):
    """
    E.g. data["pcsAPhase"] -> { vol, amp, actPwr, reactPwr, apparentPwr }
    """

    def __init__(self, coordinator, phase: str, detail_key: str, name_suffix: str, unit, device_type: str):
        super().__init__(coordinator, f"Phase {phase} {name_suffix}", device_type)
        self.phase = phase
        self.detail_key = detail_key
        self._attr_native_unit_of_measurement = unit
        self._unique_id = f"{coordinator.device_sn}_{device_type}_pcs{phase}Phase_{detail_key}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        root_key = f"pcs{self.phase}Phase"
        obj = self.coordinator.data.get(root_key, {})
        return obj.get(self.detail_key, 0)


# ------------------------------------------------------------------------------
# EcoFlowNestedSensor (z. B. sectorA.tempCurr)
# ------------------------------------------------------------------------------
class EcoFlowNestedSensor(EcoFlowBaseSensor):
    def __init__(self, coordinator, root_key: str, friendly_name: str, sub_key: str, unit, device_type: str):
        super().__init__(coordinator, friendly_name, device_type)
        self.root_key = root_key
        self.sub_key = sub_key
        self._attr_native_unit_of_measurement = unit
        self._unique_id = f"{coordinator.device_sn}_{device_type}_{root_key}_{sub_key}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        root_obj = self.coordinator.data.get(self.root_key, {})
        return root_obj.get(self.sub_key, 0)


# ------------------------------------------------------------------------------
# EcoFlowHeatPumpSensor (hpMaster)
# ------------------------------------------------------------------------------
class EcoFlowHeatPumpSensor(EcoFlowBaseSensor):
    def __init__(self, coordinator, root_key: str, friendly_name: str, device_type: str):
        super().__init__(coordinator, friendly_name, device_type)
        self.root_key = root_key
        self._unique_id = f"{coordinator.device_sn}_{device_type}_{root_key}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def native_unit_of_measurement(self):
        return TEMP_CELSIUS

    @property
    def state(self):
        root_obj = self.coordinator.data.get(self.root_key, {})
        return root_obj.get("tempInlet", 0)

    @property
    def extra_state_attributes(self):
        root_obj = self.coordinator.data.get(self.root_key, {})
        return {
            "tempOutlet": root_obj.get("tempOutlet"),
            "tempAmbient": root_obj.get("tempAmbient")
        }


# ------------------------------------------------------------------------------
# EcoFlowErrorCodeSensor (emsErrCode -> { errCode: [601, ...] })
# ------------------------------------------------------------------------------
class EcoFlowErrorCodeSensor(EcoFlowBaseSensor):
    def __init__(self, coordinator, root_key: str, friendly_name: str, device_type: str):
        super().__init__(coordinator, friendly_name, device_type)
        self.root_key = root_key
        self._unique_id = f"{coordinator.device_sn}_{device_type}_{root_key}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        err_obj = self.coordinator.data.get(self.root_key, {})
        codes = err_obj.get("errCode", [])
        return codes[0] if codes else 0

    @property
    def extra_state_attributes(self):
        err_obj = self.coordinator.data.get(self.root_key, {})
        return {
            "all_error_codes": err_obj.get("errCode", [])
        }


# ------------------------------------------------------------------------------
# EcoFlowHrEnergyStreamSensor (hrEnergyStream -> [ {temp, hrPwr} ])
# ------------------------------------------------------------------------------
class EcoFlowHrEnergyStreamSensor(EcoFlowBaseSensor):
    def __init__(self, coordinator, friendly_name: str, device_type: str):
        super().__init__(coordinator, friendly_name, device_type)
        self._unique_id = f"{coordinator.device_sn}_{device_type}_hrEnergyStream"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def native_unit_of_measurement(self):
        return POWER_WATT

    @property
    def state(self):
        arr = self.coordinator.data.get("hrEnergyStream", [])
        if len(arr) > 0:
            return arr[0].get("hrPwr", 0)
        return 0

    @property
    def extra_state_attributes(self):
        arr = self.coordinator.data.get("hrEnergyStream", [])
        if len(arr) > 0:
            return {"temp": arr[0].get("temp")}
        return {}


# ------------------------------------------------------------------------------
# EcoFlowMPPTSensor (mpptHeartBeat -> mpptPv array)
# ------------------------------------------------------------------------------
class EcoFlowMPPTSensor(EcoFlowBaseSensor):
    def __init__(self, coordinator, index: int, device_type="PowerOcean"):
        super().__init__(coordinator, f"MPPT PV[{index}]", device_type)
        self.index = index
        self._unique_id = f"{coordinator.device_sn}_{device_type}_mpptPv_{index}"

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
# EcoFlowHistorySensor (historical_data => "Self-sufficiency")
# ------------------------------------------------------------------------------
class EcoFlowHistorySensor(EcoFlowBaseSensor):
    def __init__(self, coordinator, friendly_name: str, device_type: str):
        super().__init__(coordinator, friendly_name, device_type)
        self._unique_id = f"{coordinator.device_sn}_{device_type}_history"

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

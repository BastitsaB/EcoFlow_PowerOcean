"""
sensor.py – A comprehensive sensor setup for EcoFlow PowerOcean, covering nearly all documented fields.
Comments in English, rest in German.
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
    This function collects all sensor entities based on the data
    that EcoFlow exposes: Phases (A/B/C), Battery (SoC, power),
    PV info (MPPT, phases, reactive power, etc.), Heat pump sectors,
    EV Charger (PowerPulse), error codes, historical data, etc.
    """
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Collect all sensor entities in a list, then pass them to async_add_entities().
    sensor_entities = []

    # --------------------------------------------------
    # 1) SYSTEM / BATTERY / GRID
    # --------------------------------------------------

    # sysLoadPwr: the total load in the system
    sensor_entities.append(
        EcoFlowSingleValueSensor(
            coordinator,
            key="sysLoadPwr",
            friendly_name="System Load Power",
            unit=POWER_WATT
        )
    )
    # sysGridPwr: power flow from/to the grid (can be negative or positive)
    sensor_entities.append(
        EcoFlowSingleValueSensor(
            coordinator,
            key="sysGridPwr",
            friendly_name="System Grid Power",
            unit=POWER_WATT
        )
    )
    # bpSoc: battery state of charge
    sensor_entities.append(
        EcoFlowSingleValueSensor(
            coordinator,
            key="bpSoc",
            friendly_name="Battery SoC",
            unit=PERCENTAGE
        )
    )
    # bpPwr: battery charging/discharging power
    sensor_entities.append(
        EcoFlowSingleValueSensor(
            coordinator,
            key="bpPwr",
            friendly_name="Battery Power",
            unit=POWER_WATT
        )
    )
    # mpptPwr: total PV power
    sensor_entities.append(
        EcoFlowSingleValueSensor(
            coordinator,
            key="mpptPwr",
            friendly_name="PV Power",
            unit=POWER_WATT
        )
    )

    # --------------------------------------------------
    # 2) PHASES A/B/C – MORE DETAILS
    # Each has vol, amp, actPwr, reactPwr, apparentPwr
    # in pcsAPhase, pcsBPhase, pcsCPhase
    # --------------------------------------------------

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

    # --------------------------------------------------
    # 3) PV / MPPT DETAILS (mpptHeartBeat -> mpptPv array)
    # Some devices have multiple PV inputs (index 0, 1, ...)
    # We'll assume up to 2 or 3. Adjust as needed.
    # --------------------------------------------------

    for pv_index in range(2):
        sensor_entities.append(
            EcoFlowMPPTSensor(
                coordinator,
                index=pv_index
            )
        )

    # --------------------------------------------------
    # 4) HEAT PUMP / SECTORS (sectorA, sectorB, sectorDhw, hpMaster, etc.)
    # sectorA -> {"tempCurr": ...}
    # sectorB -> {"tempCurr": ...}
    # sectorDhw -> {"tempCurr": ...}
    # hpMaster -> {"tempInlet", "tempOutlet", "tempAmbient"}
    # --------------------------------------------------

    # sectorA: temperature
    sensor_entities.append(
        EcoFlowNestedSensor(
            coordinator,
            root_key="sectorA",
            friendly_name="Sector A Temp",
            sub_key="tempCurr",
            unit=TEMP_CELSIUS
        )
    )
    # sectorB: temperature
    sensor_entities.append(
        EcoFlowNestedSensor(
            coordinator,
            root_key="sectorB",
            friendly_name="Sector B Temp",
            sub_key="tempCurr",
            unit=TEMP_CELSIUS
        )
    )
    # sectorDhw: hot water temperature
    sensor_entities.append(
        EcoFlowNestedSensor(
            coordinator,
            root_key="sectorDhw",
            friendly_name="Hot Water Temp",
            sub_key="tempCurr",
            unit=TEMP_CELSIUS
        )
    )
    # hpMaster: specialized sensor that yields inlet/outlet/ambient
    sensor_entities.append(
        EcoFlowHeatPumpSensor(
            coordinator,
            root_key="hpMaster",
            friendly_name="Heat Pump Master"
        )
    )

    # --------------------------------------------------
    # 5) ERROR CODES (emsErrCode, etc.)
    # emsErrCode -> { "errCode": [601, ...] }
    # --------------------------------------------------

    sensor_entities.append(
        EcoFlowErrorCodeSensor(
            coordinator,
            root_key="emsErrCode",
            friendly_name="EMS Error Code"
        )
    )

    # --------------------------------------------------
    # 6) POWERGLOW: hrEnergyStream -> [ { "temp": 22, "hrPwr": 0 } ]
    # --------------------------------------------------

    sensor_entities.append(
        EcoFlowHrEnergyStreamSensor(
            coordinator,
            friendly_name="PowerGlow HR Energy Stream"
        )
    )

    # --------------------------------------------------
    # 7) POWERPULSE / EV CHARGER
    # evPwr, chargingStatus, errorCode (maybe "errorCode": "AAAAAAAAAAA=") 
    # --------------------------------------------------

    sensor_entities.append(
        EcoFlowSingleValueSensor(
            coordinator,
            key="evPwr",
            friendly_name="EV Power",
            unit=POWER_WATT
        )
    )
    sensor_entities.append(
        EcoFlowSingleValueSensor(
            coordinator,
            key="chargingStatus",
            friendly_name="EV Charging Status",
            unit=None
        )
    )
    sensor_entities.append(
        EcoFlowSingleValueSensor(
            coordinator,
            key="errorCode",
            friendly_name="EV Error Code",
            unit=None
        )
    )

    # --------------------------------------------------
    # 8) HISTORICAL DATA
    # The coordinator might store it in data["historical_data"].
    # We'll make a specialized sensor that picks out "Self-sufficiency"
    # or other stats from the "week" summary.
    # --------------------------------------------------

    sensor_entities.append(
        EcoFlowHistorySensor(
            coordinator,
            friendly_name="Historical Data (Week)"
        )
    )

    # --------------------------------------------------
    # Füge hier gerne weitere Sensors hinzu,
    # falls du mehr Felder aus der Doku gefunden hast.
    # --------------------------------------------------

    # Now we add them all at once.
    async_add_entities(sensor_entities)


# ------------------------------------------------------------------------------
# Gemeinsame Basisklasse
# ------------------------------------------------------------------------------

class EcoFlowBaseSensor(SensorEntity):
    """
    This base sensor ties into the coordinator's data property,
    which is a merged dictionary containing:
      - All Quotas
      - BMS data
      - Historical data (under data["historical_data"])
      - Possibly MQTT updates
    """

    def __init__(self, coordinator, sensor_name: str):
        self.coordinator = coordinator
        self._attr_name = sensor_name

    @property
    def device_info(self):
        """
        By default, we group everything under a single "EcoFlow PowerOcean (All Data)" device.
        If you want multiple devices, you can split them as in previous examples.
        """
        return {
            "identifiers": {(DOMAIN, self.coordinator.device_sn)},
            "name": "EcoFlow PowerOcean (All Data)",
            "manufacturer": "EcoFlow",
            "model": "PowerOcean",
            "sw_version": "1.0.0",
        }

    @property
    def should_poll(self) -> bool:
        """We rely on the DataUpdateCoordinator, so no direct polling here."""
        return False

    async def async_update(self):
        """Request coordinator to refresh data."""
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self):
        """When the entity is added to Home Assistant, register a callback to update state."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

# ------------------------------------------------------------------------------
# Sensor für einzelne "Key=Value"
# ------------------------------------------------------------------------------

class EcoFlowSingleValueSensor(EcoFlowBaseSensor):
    """Represents a sensor that reads a single top-level key from coordinator.data."""

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
# Sensor für verschachtelte objekte: data[root_key][sub_key]
# ------------------------------------------------------------------------------

class EcoFlowNestedSensor(EcoFlowBaseSensor):
    """
    For example, sectorA -> { "tempCurr": 22.7 }
    We pass root_key="sectorA", sub_key="tempCurr".
    """

    def __init__(self, coordinator, root_key: str, friendly_name: str, sub_key: str, unit):
        super().__init__(coordinator, f"{friendly_name}")
        self.root_key = root_key
        self.sub_key = sub_key
        self._attr_native_unit_of_measurement = unit
        self._unique_id = f"{coordinator.device_sn}_{root_key}_{sub_key}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        root_obj = self.coordinator.data.get(self.root_key, {})
        return root_obj.get(self.sub_key, 0)

# ------------------------------------------------------------------------------
# Sensor für Phasendetails (A/B/C) => pcsAPhase, pcsBPhase, pcsCPhase
# ------------------------------------------------------------------------------
class EcoFlowPhaseDetailSensor(EcoFlowBaseSensor):
    """
    Reads keys like vol, amp, actPwr, reactPwr, apparentPwr from:
    data["pcsAPhase"], data["pcsBPhase"], data["pcsCPhase"].
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
# Sensor für HeatPump (hpMaster)
# ------------------------------------------------------------------------------
class EcoFlowHeatPumpSensor(EcoFlowBaseSensor):
    """
    e.g. hpMaster -> { "tempInlet": 22.5, "tempOutlet": 22.5, "tempAmbient": -3270 }
    We'll show 'tempInlet' as the main state, others as attributes.
    """

    def __init__(self, coordinator, root_key: str, friendly_name: str):
        super().__init__(coordinator, friendly_name)
        self.root_key = root_key
        self._unique_id = f"{coordinator.device_sn}_{root_key}"

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
# Sensor für Error-Codes (z.B. emsErrCode -> { "errCode": [601, ...] })
# ------------------------------------------------------------------------------
class EcoFlowErrorCodeSensor(EcoFlowBaseSensor):
    """Reads an error code array from coordinator.data[root_key]."""

    def __init__(self, coordinator, root_key: str, friendly_name: str):
        super().__init__(coordinator, friendly_name)
        self.root_key = root_key
        self._unique_id = f"{coordinator.device_sn}_{root_key}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        err_obj = self.coordinator.data.get(self.root_key, {})
        codes = err_obj.get("errCode", [])
        if codes:
            return codes[0]
        return 0

    @property
    def extra_state_attributes(self):
        err_obj = self.coordinator.data.get(self.root_key, {})
        return {
            "all_error_codes": err_obj.get("errCode", [])
        }

# ------------------------------------------------------------------------------
# Sensor für HR Energy Stream (PowerGlow)
# ------------------------------------------------------------------------------
class EcoFlowHrEnergyStreamSensor(EcoFlowBaseSensor):
    """
    hrEnergyStream -> [ { "temp": 22, "hrPwr": 0 } ]
    We'll use 'hrPwr' as state, 'temp' as attribute.
    """

    def __init__(self, coordinator, friendly_name: str):
        super().__init__(coordinator, friendly_name)
        self._unique_id = f"{coordinator.device_sn}_hrEnergyStream"

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
# Sensor für MPPT-Eingänge (mpptHeartBeat -> [ { "mpptPv": [ {vol, amp, pwr}, ...] } ])
# ------------------------------------------------------------------------------
class EcoFlowMPPTSensor(EcoFlowBaseSensor):
    """
    Reads mpptHeartBeat[0].mpptPv[index] -> { vol, amp, pwr }.
    We'll use 'pwr' as state, and 'vol'/'amp' as attributes.
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
        # Usually mpptHeartBeat = [ { "mpptPv": [ {vol, amp, pwr}, ... ] } ]
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
# Historische Daten (z. B. "Self-sufficiency") unter coordinator.data["historical_data"]
# ------------------------------------------------------------------------------
class EcoFlowHistorySensor(EcoFlowBaseSensor):
    """
    Displays a key metric (e.g. "Self-sufficiency") from the historical data.
    Also exposes all raw data as attributes.
    """

    def __init__(self, coordinator, friendly_name: str):
        super().__init__(coordinator, friendly_name)
        self._unique_id = f"{coordinator.device_sn}_history"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        """
        The coordinator might store historical data in data["historical_data"] -> { "data": [ {...} ] }
        We look for "Self-sufficiency" or any other indexName you'd like to highlight.
        """
        hist_data = self.coordinator.data.get("historical_data", {})
        data_arr = hist_data.get("data", [])
        for item in data_arr:
            if item.get("indexName") == "Self-sufficiency":
                return item.get("indexValue", 0)
        return 0

    @property
    def extra_state_attributes(self):
        """Expose the entire raw historical data block."""
        hist_data = self.coordinator.data.get("historical_data", {})
        return {
            "raw_history_data": hist_data
        }

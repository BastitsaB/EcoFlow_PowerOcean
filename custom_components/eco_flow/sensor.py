import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    UnitOfPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfReactivePower,
    UnitOfApparentPower,
    UnitOfTemperature,
    PERCENTAGE,
)
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    sensor_entities = []

    # General System Sensors
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="sysLoadPwr",
        friendly_name="System Load Power",
        unit=UnitOfPower.WATT,
        device_type="System"
    ))
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="sysGridPwr",
        friendly_name="System Grid Power",
        unit=UnitOfPower.WATT,
        device_type="System"
    ))
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="bpPwr",
        friendly_name="Battery Power",
        unit=UnitOfPower.WATT,
        device_type="Battery"
    ))
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="ems_change_report.bpSoc",
        friendly_name="Battery SoC",
        unit=PERCENTAGE,
        device_type="Battery"
    ))

    # Phase Sensors
    phase_letters = ["A", "B", "C"]
    phase_detail_keys = [
        ("vol", "Voltage", UnitOfElectricPotential.VOLT),
        ("amp", "Current", UnitOfElectricCurrent.AMPERE),
        ("actPwr", "Active Power", UnitOfPower.WATT),
        ("reactPwr", "Reactive Power", UnitOfReactivePower.VOLT_AMPERE_REACTIVE),
        ("apparentPwr", "Apparent Power", UnitOfApparentPower.VOLT_AMPERE),
    ]
    for phase in phase_letters:
        for detail_key, detail_name, detail_unit in phase_detail_keys:
            sensor_entities.append(EcoFlowPhaseDetailSensor(
                coordinator,
                phase=phase,
                detail_key=detail_key,
                name_suffix=detail_name,
                unit=detail_unit,
                device_type="Phase"
            ))

    # MPPT Sensors
    sensor_entities.append(EcoFlowNestedSensor(
        coordinator,
        root_key="mpptHeartBeat[0].mpptPv[0]",
        friendly_name="MPPT PV1 Power",
        sub_key="pwr",
        unit=UnitOfPower.WATT,
        device_type="MPPT"
    ))
    sensor_entities.append(EcoFlowNestedSensor(
        coordinator,
        root_key="mpptHeartBeat[0].mpptPv[1]",
        friendly_name="MPPT PV2 Power",
        sub_key="pwr",
        unit=UnitOfPower.WATT,
        device_type="MPPT"
    ))
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="mpptPwr",
        friendly_name="MPPT Total Power",
        unit=UnitOfPower.WATT,
        device_type="MPPT"
    ))

    # Self-Sufficiency Sensor
    sensor_entities.append(EcoFlowHistorySensor(
        coordinator,
        friendly_name="Self-Sufficiency",
        device_type="History"
    ))

    async_add_entities(sensor_entities)


class EcoFlowBaseSensor(SensorEntity):
    """
    Base sensor with device_type for multi-device grouping in HA.
    """

    def __init__(self, coordinator, sensor_name: str, device_type: str):
        self.coordinator = coordinator
        self._attr_name = sensor_name
        self.device_type = device_type

    @property
    def device_info(self):
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


class EcoFlowSingleValueSensor(EcoFlowBaseSensor):
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


class EcoFlowPhaseDetailSensor(EcoFlowBaseSensor):
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

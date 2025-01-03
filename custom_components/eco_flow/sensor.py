import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    UnitOfPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfReactivePower,
    UnitOfApparentPower,
    UnitOfTemperature,
    PERCENTAGE
)
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    sensor_entities = []

    # System Load Power
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="sysLoadPwr",
        friendly_name="System Load Power",
        unit=UnitOfPower.WATT,
        device_type="PowerOcean"
    ))

    # Grid Power
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="sysGridPwr",
        friendly_name="Grid Power",
        unit=UnitOfPower.WATT,
        device_type="PowerOcean"
    ))

    # Battery Power
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="bpPwr",
        friendly_name="Battery Power",
        unit=UnitOfPower.WATT,
        device_type="PowerOcean"
    ))

    # Battery SoC
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="ems_change_report.bpSoc",
        friendly_name="Battery State of Charge",
        unit=PERCENTAGE,
        device_type="PowerOcean"
    ))

    # SG Mode
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="ems_change_report.emsSgReady.emsSgMode",
        friendly_name="SG Mode",
        unit=None,
        device_type="PowerOcean"
    ))

    # SG Parameters
    for idx, sg_param in enumerate(coordinator.data.get("ems_change_report.emsSgReady.emsSgParam", [])):
        sensor_entities.append(EcoFlowNestedSensor(
            coordinator,
            root_key=f"ems_change_report.emsSgReady.emsSgParam[{idx}]",
            friendly_name=f"SG Parameter {idx+1} Power",
            sub_key="emsSgPwr",
            unit=UnitOfPower.WATT,
            device_type="PowerOcean"
        ))
        sensor_entities.append(EcoFlowNestedSensor(
            coordinator,
            root_key=f"ems_change_report.emsSgReady.emsSgParam[{idx}]",
            friendly_name=f"SG Parameter {idx+1} Status",
            sub_key="emsSgStat",
            unit=None,
            device_type="PowerOcean"
        ))
        if "emsSgSoc" in sg_param:  # Optional
            sensor_entities.append(EcoFlowNestedSensor(
                coordinator,
                root_key=f"ems_change_report.emsSgReady.emsSgParam[{idx}]",
                friendly_name=f"SG Parameter {idx+1} SOC",
                sub_key="emsSgSoc",
                unit=PERCENTAGE,
                device_type="PowerOcean"
            ))

    # Phase Sensors
    for phase_name, phase_data in [("A", "pcsAPhase"), ("B", "pcsBPhase"), ("C", "pcsCPhase")]:
        for key, label, unit in [
            ("vol", "Voltage", UnitOfElectricPotential.VOLT),
            ("amp", "Current", UnitOfElectricCurrent.AMPERE),
            ("actPwr", "Active Power", UnitOfPower.WATT),
            ("reactPwr", "Reactive Power", UnitOfReactivePower.VOLT_AMPERE_REACTIVE),
            ("apparentPwr", "Apparent Power", UnitOfApparentPower.VOLT_AMPERE)
        ]:
            sensor_entities.append(EcoFlowNestedSensor(
                coordinator,
                root_key=phase_data,
                friendly_name=f"Phase {phase_name} {label}",
                sub_key=key,
                unit=unit,
                device_type="PowerOcean"
            ))

    # MPPT Sensors
    mppt_data = coordinator.data.get("mpptHeartBeat", [])
    for idx, mppt in enumerate(mppt_data):
        for pv_idx, pv_data in enumerate(mppt.get("mpptPv", [])):
            sensor_entities.append(EcoFlowNestedSensor(
                coordinator,
                root_key=f"mpptHeartBeat[{idx}].mpptPv[{pv_idx}]",
                friendly_name=f"MPPT {idx+1} PV {pv_idx+1} Power",
                sub_key="pwr",
                unit=UnitOfPower.WATT,
                device_type="PowerOcean"
            ))
            sensor_entities.append(EcoFlowNestedSensor(
                coordinator,
                root_key=f"mpptHeartBeat[{idx}].mpptPv[{pv_idx}]",
                friendly_name=f"MPPT {idx+1} PV {pv_idx+1} Voltage",
                sub_key="vol",
                unit=UnitOfElectricPotential.VOLT,
                device_type="PowerOcean"
            ))
            sensor_entities.append(EcoFlowNestedSensor(
                coordinator,
                root_key=f"mpptHeartBeat[{idx}].mpptPv[{pv_idx}]",
                friendly_name=f"MPPT {idx+1} PV {pv_idx+1} Current",
                sub_key="amp",
                unit=UnitOfElectricCurrent.AMPERE,
                device_type="PowerOcean"
            ))

    # Total MPPT Power
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="mpptPwr",
        friendly_name="MPPT Total Power",
        unit=UnitOfPower.WATT,
        device_type="PowerOcean"
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

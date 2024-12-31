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

    # Example grouping into separate devices:
    # 1) PowerOcean device: sysLoadPwr, sysGridPwr, bpSoc, bpPwr, mpptPwr, phases
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="sysLoadPwr",
        friendly_name="System Load Power",
        unit=UnitOfPower.WATT,
        device_type="PowerOcean"
    ))
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="sysGridPwr",
        friendly_name="System Grid Power",
        unit=UnitOfPower.WATT,
        device_type="PowerOcean"
    ))
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
        unit=UnitOfPower.WATT,
        device_type="PowerOcean"
    ))
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="mpptPwr",
        friendly_name="PV Power",
        unit=UnitOfPower.WATT,
        device_type="PowerOcean"
    ))

    # Phases
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
                device_type="PowerOcean"
            ))

    # 2) PowerHeat
    sensor_entities.append(EcoFlowNestedSensor(
        coordinator,
        root_key="sectorA",
        friendly_name="Sector A Temp",
        sub_key="tempCurr",
        unit=UnitOfTemperature.CELSIUS,
        device_type="PowerHeat"
    ))
    sensor_entities.append(EcoFlowNestedSensor(
        coordinator,
        root_key="sectorB",
        friendly_name="Sector B Temp",
        sub_key="tempCurr",
        unit=UnitOfTemperature.CELSIUS,
        device_type="PowerHeat"
    ))
    sensor_entities.append(EcoFlowNestedSensor(
        coordinator,
        root_key="sectorDhw",
        friendly_name="Hot Water Temp",
        sub_key="tempCurr",
        unit=UnitOfTemperature.CELSIUS,
        device_type="PowerHeat"
    ))
    sensor_entities.append(EcoFlowHeatPumpSensor(
        coordinator,
        root_key="hpMaster",
        friendly_name="Heat Pump Master",
        device_type="PowerHeat"
    ))
    sensor_entities.append(EcoFlowErrorCodeSensor(
        coordinator,
        root_key="emsErrCode",
        friendly_name="EMS Error Code",
        device_type="PowerHeat"
    ))

    # 3) PowerGlow
    sensor_entities.append(EcoFlowHrEnergyStreamSensor(
        coordinator,
        friendly_name="PowerGlow HR Energy Stream",
        device_type="PowerGlow"
    ))

    # 4) PowerPulse
    sensor_entities.append(EcoFlowSingleValueSensor(
        coordinator,
        key="evPwr",
        friendly_name="EV Power",
        unit=UnitOfPower.WATT,
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

    # 5) PowerHistory
    sensor_entities.append(EcoFlowHistorySensor(
        coordinator,
        friendly_name="Historical Data (Week)",
        device_type="PowerHistory"
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
        return UnitOfTemperature.CELSIUS

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


class EcoFlowHrEnergyStreamSensor(EcoFlowBaseSensor):
    def __init__(self, coordinator, friendly_name: str, device_type: str):
        super().__init__(coordinator, friendly_name, device_type)
        self._unique_id = f"{coordinator.device_sn}_{device_type}_hrEnergyStream"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def native_unit_of_measurement(self):
        return UnitOfPower.WATT

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

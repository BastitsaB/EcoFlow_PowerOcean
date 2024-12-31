"""Sensor platform for EcoFlow PowerOcean."""

import logging
import requests
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import POWER_WATT
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up EcoFlow PowerOcean sensor entities."""
    coordinator = EcoFlowDataCoordinator(hass, config_entry)
    await coordinator.async_update_data()
    async_add_entities([EcoFlowPowerSensor(coordinator)], True)

class EcoFlowDataCoordinator:
    """Coordinate data updates from EcoFlow Cloud or local API."""

    def __init__(self, hass, config_entry):
        """Initialize the data coordinator."""
        self._hass = hass
        self._config_entry = config_entry
        self._data = {}
        self._api_token = config_entry.data.get("api_token")
        self._device_id = config_entry.data.get("device_id")

    async def async_update_data(self):
        """Fetch data from EcoFlow."""
        try:
            self._data = await self._hass.async_add_executor_job(self._fetch_data)
        except Exception as exc:
            _LOGGER.error("Error updating EcoFlow data: %s", exc)

    def _fetch_data(self) -> dict:
        """Blocking call to fetch data from the API."""
        # Placeholder-URL anpassen
        url = f"https://api.ecoflow.com/v1/devices/{self._device_id}/status"
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            _LOGGER.error("Error fetching EcoFlow data: %s", exc)
            return {}

    @property
    def data(self) -> dict:
        """Return the latest data."""
        return self._data

class EcoFlowPowerSensor(SensorEntity):
    """Representation of an EcoFlow sensor."""

    def __init__(self, coordinator: EcoFlowDataCoordinator):
        """Initialize the sensor entity."""
        self._coordinator = coordinator
        self._state = None
        self._attr_name = "EcoFlow Current Power"
        self._attr_native_unit_of_measurement = POWER_WATT

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    async def async_update(self):
        """Request latest data from the coordinator."""
        await self._coordinator.async_update_data()
        data = self._coordinator.data
        # Passe diesen Key an die JSON-Struktur an
        self._state = data.get("current_power", 0)

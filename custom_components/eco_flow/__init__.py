"""
__init__.py – Initialize the EcoFlow PowerOcean integration,
fetch MQTT cert if needed, and set up the sensor platform.
"""

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import EcoFlowDataCoordinator
from .mqtt_handler import EcoFlowMQTTHandler

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ecoflow_powerocean"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EcoFlow PowerOcean from a config entry."""
    coordinator = EcoFlowDataCoordinator(hass, entry)

    # 1) If MQTT is enabled, fetch the certification first (blocking call)
    if entry.data.get("mqtt_enabled", False):
        await hass.async_add_executor_job(coordinator.fetch_mqtt_certification)

    # 2) Initialize the coordinator (REST calls). This sets coordinator.data
    await coordinator.async_config_entry_first_refresh()

    # store
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # 3) If MQTT is enabled, set up the MQTT handler
    if entry.data.get("mqtt_enabled", False):
        mqtt_handler = EcoFlowMQTTHandler(hass, coordinator)
        coordinator.mqtt_handler = mqtt_handler
        await hass.async_add_executor_job(mqtt_handler.connect)

    # 4) Forward to sensor platform
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload EcoFlow PowerOcean config entry."""
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)

    if coordinator and getattr(coordinator, "mqtt_handler", None):
        coordinator.mqtt_handler.stop()

    return True

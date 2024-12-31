"""
__init__.py – Initialize the EcoFlow PowerOcean integration,
now using a proper await for async_forward_entry_setup instead of create_task.
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

    # If MQTT is enabled, fetch the certificate
    if entry.data.get("mqtt_enabled", False):
        await hass.async_add_executor_job(coordinator.fetch_mqtt_certification)

    # Start coordinator first refresh (REST calls)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Setup MQTT
    if entry.data.get("mqtt_enabled", False):
        mqtt_handler = EcoFlowMQTTHandler(hass, coordinator)
        coordinator.mqtt_handler = mqtt_handler
        await hass.async_add_executor_job(mqtt_handler.connect)

    # Properly await async_forward_entry_setup (no create_task)
    await hass.config_entries.async_forward_entry_setup(entry, "sensor")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload EcoFlow PowerOcean config entry."""
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)

    if coordinator and getattr(coordinator, "mqtt_handler", None):
        coordinator.mqtt_handler.stop()

    return True

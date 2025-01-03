"""
__init__.py – Initialize the EcoFlow PowerOcean integration with async setups.
"""

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import EcoFlowDataCoordinator
from .mqtt_handler import EcoFlowMQTTHandler

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ecoflow_powerocean"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EcoFlow PowerOcean from a config entry."""
    coordinator = EcoFlowDataCoordinator(hass, entry)

    # If MQTT is enabled, fetch the certificate
    if entry.data.get("mqtt_enabled", False):
        try:
            await hass.async_add_executor_job(coordinator.fetch_mqtt_certification)
        except Exception as e:
            _LOGGER.error("Failed to fetch MQTT certification: %s", e)
            raise ConfigEntryNotReady from e

    # Start coordinator first refresh (REST calls)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.error("Failed to refresh coordinator data: %s", e)
        raise ConfigEntryNotReady from e

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Setup MQTT
    if entry.data.get("mqtt_enabled", False):
        mqtt_handler = EcoFlowMQTTHandler(hass, coordinator)
        coordinator.mqtt_handler = mqtt_handler
        try:
            await hass.async_add_executor_job(mqtt_handler.connect)
        except Exception as e:
            _LOGGER.error("Failed to initialize MQTT: %s", e)
            raise ConfigEntryNotReady from e

    # Use the new async_forward_entry_setups method
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload EcoFlow PowerOcean config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    if unload_ok and DOMAIN in hass.data:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator and getattr(coordinator, "mqtt_handler", None):
            coordinator.mqtt_handler.stop()
    return unload_ok

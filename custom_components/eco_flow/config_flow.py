"""
config_flow.py – UI configuration flow for EcoFlow PowerOcean.
Abfragt access_key, secret_key, device_sn, mqtt_enabled.
Kommentierungen auf Englisch, rest auf Deutsch.
"""

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_ACCESS_KEY = "access_key"
CONF_SECRET_KEY = "secret_key"
CONF_DEVICE_SN = "device_sn"
CONF_MQTT_ENABLED = "mqtt_enabled"

class EcoFlowPowerOceanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EcoFlow PowerOcean."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_ACCESS_KEY: user_input[CONF_ACCESS_KEY],
                    CONF_SECRET_KEY: user_input[CONF_SECRET_KEY],
                    CONF_DEVICE_SN: user_input[CONF_DEVICE_SN],
                    CONF_MQTT_ENABLED: user_input[CONF_MQTT_ENABLED],
                },
            )

        data_schema = vol.Schema({
            vol.Required(CONF_NAME, default="EcoFlow PowerOcean"): str,
            vol.Required(CONF_ACCESS_KEY): str,
            vol.Required(CONF_SECRET_KEY): str,
            vol.Required(CONF_DEVICE_SN): str,
            vol.Optional(CONF_MQTT_ENABLED, default=False): bool,
        })

        return self.async_show_form(step_id="user", data_schema=data_schema)

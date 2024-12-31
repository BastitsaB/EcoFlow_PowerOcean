"""Config flow for EcoFlow PowerOcean integration."""

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Beispiel-Konfigurationsschlüssel
CONF_API_TOKEN = "api_token"
CONF_DEVICE_ID = "device_id"

class EcoFlowPowerOceanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EcoFlow PowerOcean."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            # Optional: Validierung, ob API-Token oder Device-ID stimmen
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_API_TOKEN: user_input[CONF_API_TOKEN],
                    CONF_DEVICE_ID: user_input[CONF_DEVICE_ID]
                },
            )

        data_schema = vol.Schema({
            vol.Required(CONF_NAME, default="EcoFlow PowerOcean"): str,
            vol.Required(CONF_API_TOKEN): str,
            vol.Required(CONF_DEVICE_ID): str
        })

        return self.async_show_form(step_id="user", data_schema=data_schema)

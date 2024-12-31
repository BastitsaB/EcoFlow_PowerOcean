"""Config flow for EcoFlow PowerOcean integration."""

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_ACCESS_KEY = "access_key"
CONF_SECRET_KEY = "secret_key"
CONF_DEVICE_SN  = "device_sn"

class EcoFlowPowerOceanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EcoFlow PowerOcean."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            # Du könntest hier eine Test-Request an die API senden, um die Keys zu validieren
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_ACCESS_KEY: user_input[CONF_ACCESS_KEY],
                    CONF_SECRET_KEY: user_input[CONF_SECRET_KEY],
                    CONF_DEVICE_SN : user_input[CONF_DEVICE_SN]
                },
            )

        data_schema = vol.Schema({
            vol.Required(CONF_NAME, default="EcoFlow PowerOcean"): str,
            vol.Required(CONF_ACCESS_KEY): str,
            vol.Required(CONF_SECRET_KEY): str,
            vol.Required(CONF_DEVICE_SN): str
        })

        return self.async_show_form(step_id="user", data_schema=data_schema)

"""Config flow for Israeli Premier League integration."""
from __future__ import annotations
import logging
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_API_KEY, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DEFAULT_API_KEY
from .api import IsraeliPremierLeagueAPI

_LOGGER = logging.getLogger(__name__)

class IsraeliPremierLeagueConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            api = IsraeliPremierLeagueAPI(self.hass, user_input[CONF_API_KEY])
            if await api.async_validate_key():
                return self.async_create_entry(
                    title="ליגת העל",
                    data={CONF_API_KEY: user_input[CONF_API_KEY]}
                )
            errors["base"] = "invalid_auth"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY, default=DEFAULT_API_KEY): str
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return IsraeliPremierLeagueOptionsFlow(config_entry)

class IsraeliPremierLeagueOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
            }),
        )

"""Config flow - Urgences Quebec.

Setup initial minimal (instance unique) - la selection region/installations
se fait dans l'options flow (options_flow.py), reconfigurable en tout temps
sans retirer l'integration.

TODO prochaine session :
- Etape proximite (selector.location + "N plus proches") dans l'options
  flow, une fois le geocodage des 137 installations fait (voir PROGRESS.md)
"""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .options_flow import UrgencesQuebecOptionsFlow


class UrgencesQuebecConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow - instance unique (une seule entree, filtree via options)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="Urgences Québec", data={})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> UrgencesQuebecOptionsFlow:
        return UrgencesQuebecOptionsFlow()

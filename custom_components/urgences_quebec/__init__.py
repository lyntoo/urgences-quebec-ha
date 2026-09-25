"""Integration Urgences Quebec - temps d'attente aux urgences (donnees MSSS)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_SHOW_DASHBOARD,
    DOMAIN,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    URL_BASE,
    WEBCOMPONENT_NAME,
)
from .coordinator import UrgencesQuebecCoordinator

PLATFORMS = ["sensor"]

FRONTEND_PATH = Path(__file__).parent / "frontend"
PANEL_JS_PATH = FRONTEND_PATH / "urgences-quebec-panel.js"


def _panel_js_version() -> str:
    """Hash du JS du panneau - cache-busting automatique a chaque deploiement."""
    return hashlib.md5(PANEL_JS_PATH.read_bytes()).hexdigest()[:8]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = UrgencesQuebecCoordinator(hass)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Panneau dashboard - strictement optionnel (toggle "show_dashboard" de
    # l'options flow). Reevalue a chaque setup/reload, donc suit le toggle
    # sans logique separee. API publique/stable (panel_custom), pas de
    # depedance a une carte tierce - voir PROGRESS.md pour le choix
    # d'architecture (panneau custom plutot que dashboard Lovelace auto-
    # genere, qui aurait depedu d'API privees).
    if entry.options.get(CONF_SHOW_DASHBOARD, False):
        await _async_register_panel(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
        _async_unregister_panel(hass)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recharge l'entree quand l'options flow est sauvegarde."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_panel(hass: HomeAssistant) -> None:
    if hass.data.get(f"{DOMAIN}_panel_registered"):
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(FRONTEND_PATH), cache_headers=True)]
    )
    version = await hass.async_add_executor_job(_panel_js_version)

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=WEBCOMPONENT_NAME,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=f"{URL_BASE}/urgences-quebec-panel.js?v={version}",
        embed_iframe=False,
        require_admin=False,
    )
    hass.data[f"{DOMAIN}_panel_registered"] = True


def _async_unregister_panel(hass: HomeAssistant) -> None:
    if not hass.data.get(f"{DOMAIN}_panel_registered"):
        return
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    hass.data[f"{DOMAIN}_panel_registered"] = False

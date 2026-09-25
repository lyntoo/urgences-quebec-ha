"""Options flow - Urgences Quebec.

3 champs de filtre (regions, dashboard, position+proximite) a l'etape
"init", puis selection precise des installations a l'etape "installations"
- pre-remplie avec les N installations les plus proches si une position et
un nombre sont fournis, mais toujours modifiable manuellement.
"""
from __future__ import annotations

from homeassistant.config_entries import OptionsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import voluptuous as vol

from .const import (
    CONF_INSTALLATIONS,
    CONF_LOCATION,
    CONF_NUM_NEAREST,
    CONF_REGIONS,
    CONF_SELECT_ALL,
    CONF_SHOW_DASHBOARD,
    DOMAIN,
)
from .geo import async_load_installations_geo, haversine_km


class UrgencesQuebecOptionsFlow(OptionsFlow):
    """Options flow - pas de __init__ custom (pattern HA 2025.12+, voir PROGRESS.md)."""

    def __init__(self) -> None:
        self._selected_regions: list[str] = []
        self._location: dict | None = None
        self._num_nearest: int = 0
        self._show_dashboard: bool = False
        self._select_all: bool = False

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        regions = sorted({inst.region for inst in coordinator.data.values() if inst.region})

        if user_input is not None:
            self._selected_regions = user_input.get(CONF_REGIONS, [])
            self._show_dashboard = user_input.get(CONF_SHOW_DASHBOARD, False)
            self._location = user_input.get(CONF_LOCATION)
            self._num_nearest = user_input.get(CONF_NUM_NEAREST, 0)
            self._select_all = user_input.get(CONF_SELECT_ALL, False)
            return await self.async_step_installations()

        current_regions = self.config_entry.options.get(CONF_REGIONS, [])
        current_dashboard = self.config_entry.options.get(CONF_SHOW_DASHBOARD, False)
        current_location = self.config_entry.options.get(
            CONF_LOCATION,
            {
                "latitude": self.hass.config.latitude,
                "longitude": self.hass.config.longitude,
            },
        )
        current_num_nearest = self.config_entry.options.get(CONF_NUM_NEAREST, 0)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_REGIONS, default=current_regions): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=regions,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_LOCATION, default=current_location
                    ): selector.LocationSelector(selector.LocationSelectorConfig(radius=False)),
                    vol.Optional(
                        CONF_NUM_NEAREST, default=current_num_nearest
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0, max=20, step=1, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(
                        CONF_SHOW_DASHBOARD, default=current_dashboard
                    ): selector.BooleanSelector(),
                    vol.Optional(CONF_SELECT_ALL, default=False): selector.BooleanSelector(),
                }
            ),
            description_placeholders={"total_regions": str(len(regions))},
        )

    async def async_step_installations(self, user_input: dict | None = None) -> FlowResult:
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]

        candidats = [
            inst
            for inst in coordinator.data.values()
            if not self._selected_regions or inst.region in self._selected_regions
        ]

        # Tri par proximite si une position + un nombre > 0 sont fournis,
        # sinon tri alphabetique (comportement precedent, inchange).
        geo_data: dict[str, dict] = {}
        nearest_defaults: list[str] = []
        if self._location and self._num_nearest > 0:
            geo_data = await async_load_installations_geo(self.hass)
            avec_distance = []
            for inst in candidats:
                geo = geo_data.get(inst.no_permis)
                if geo and geo.get("lat") is not None:
                    dist = haversine_km(
                        self._location["latitude"],
                        self._location["longitude"],
                        geo["lat"],
                        geo["lon"],
                    )
                    avec_distance.append((dist, inst))
            avec_distance.sort(key=lambda x: x[0])
            nearest_defaults = [inst.no_permis for _, inst in avec_distance[: self._num_nearest]]
            # Reordonner candidats : plus proches d'abord (avec distance visible),
            # puis le reste par ordre alphabetique.
            proches_ids = set(nearest_defaults)
            candidats = [inst for _, inst in avec_distance] + [
                inst for inst in candidats if inst.no_permis not in proches_ids
            ]
        else:
            candidats.sort(key=lambda i: i.nom_installation)

        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_REGIONS: self._selected_regions,
                    CONF_SHOW_DASHBOARD: self._show_dashboard,
                    CONF_LOCATION: self._location,
                    CONF_NUM_NEAREST: self._num_nearest,
                    CONF_INSTALLATIONS: user_input.get(CONF_INSTALLATIONS, []),
                }
            )

        # Priorite des defauts : "Tout selectionner" (2026-09-25, demande
        # utilisateur) > N plus proches > selection precedente sauvegardee
        # > liste vide. "Tout selectionner" pre-coche tous les candidats
        # (deja filtres par region) pour permettre de decocher les
        # exceptions individuellement, plutot que de tout cocher un par un.
        if self._select_all:
            current_installations = [inst.no_permis for inst in candidats]
        elif nearest_defaults:
            current_installations = nearest_defaults
        else:
            current_installations = self.config_entry.options.get(CONF_INSTALLATIONS, [])

        def _label(inst) -> str:
            geo = geo_data.get(inst.no_permis)
            if geo and geo.get("lat") is not None and self._location:
                dist = haversine_km(
                    self._location["latitude"],
                    self._location["longitude"],
                    geo["lat"],
                    geo["lon"],
                )
                return f"{inst.nom_installation} ({inst.region}) — {dist:.0f} km"
            return f"{inst.nom_installation} ({inst.region})"

        return self.async_show_form(
            step_id="installations",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INSTALLATIONS, default=current_installations
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=inst.no_permis, label=_label(inst)
                                )
                                for inst in candidats
                            ],
                            multiple=True,
                            # Liste a cocher (pas dropdown) - demande explicite
                            # (2026-09-25) : eviter l'aller-retour ouvrir/choisir/
                            # fermer repete d'un dropdown pour des selections
                            # multiples, tout est visible et cochable d'un coup.
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            description_placeholders={"total_candidats": str(len(candidats))},
        )

"""Sensors - Urgences Quebec.

Scaffold (2026-09-24) : classes d'entites reelles, mais aucune installation
n'est encore creee par defaut - la liste vient de entry.options[CONF_INSTALLATIONS],
qui sera peuplee par l'options flow (pas encore implemente). Tant que l'options
flow n'existe pas, ce fichier ne cree donc aucune entite (liste vide), plutot
que de creer les 137 installations par defaut (mauvais defaut pour une vraie
installation - voir PROGRESS.md pour le filtrage prevu par region/proximite).
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_INSTALLATIONS, DOMAIN
from .coordinator import UrgencesQuebecCoordinator
from .geo import async_load_installations_geo


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UrgencesQuebecCoordinator = hass.data[DOMAIN][entry.entry_id]
    selected: list[str] = entry.options.get(CONF_INSTALLATIONS, [])

    # Charge une fois les adresses (pour l'affichage sous le nom de
    # l'appareil - demande utilisateur 2026-09-25). I/O bloquant, fait ici
    # (setup, pas un access repete) plutot que dans une property sync.
    geo_data = await async_load_installations_geo(hass)

    entities: list[SensorEntity] = []
    for no_permis in selected:
        if no_permis not in coordinator.data:
            continue
        entities.append(TempsAttenteSensor(coordinator, no_permis, geo_data))
        entities.append(OccupationSensor(coordinator, no_permis, geo_data))
        entities.append(Patients24hSensor(coordinator, no_permis, geo_data))

    async_add_entities(entities)


class _BaseInstallationEntity(CoordinatorEntity[UrgencesQuebecCoordinator], SensorEntity):
    """Base - une entite par installation."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: UrgencesQuebecCoordinator, no_permis: str, geo_data: dict
    ) -> None:
        super().__init__(coordinator)
        self._no_permis = no_permis
        self._geo = geo_data.get(no_permis)

    @property
    def _installation(self):
        return self.coordinator.data.get(self._no_permis)

    @property
    def device_info(self) -> DeviceInfo:
        inst = self._installation

        adresse_complete = None
        if self._geo:
            parts = [self._geo.get("adresse"), self._geo.get("municipalite")]
            adresse_complete = ", ".join(p for p in parts if p) or None

        return DeviceInfo(
            identifiers={(DOMAIN, self._no_permis)},
            name=inst.nom_installation if inst else self._no_permis,
            manufacturer=f"MSSS Québec — {inst.region}" if inst else "MSSS Québec",
            model=adresse_complete,
        )

    @property
    def available(self) -> bool:
        return super().available and self._installation is not None


class TempsAttenteSensor(_BaseInstallationEntity):
    """Temps d'attente estime (proxy : DMS sur civiere, en heures)."""

    _attr_translation_key = "temps_attente"
    _attr_native_unit_of_measurement = "h"
    _attr_icon = "mdi:clock-alert"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._no_permis}_temps_attente"

    @property
    def native_value(self) -> float | None:
        inst = self._installation
        return inst.dms_civiere if inst else None


class OccupationSensor(_BaseInstallationEntity):
    """Taux d'occupation (civieres occupees / fonctionnelles), en %."""

    _attr_translation_key = "occupation"
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:hospital-box"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._no_permis}_occupation"

    @property
    def native_value(self) -> float | None:
        inst = self._installation
        if not inst or not inst.civieres_fonctionnelles or inst.civieres_occupees is None:
            return None
        return round(100 * inst.civieres_occupees / inst.civieres_fonctionnelles, 1)


class Patients24hSensor(_BaseInstallationEntity):
    """Nombre de patients sur civiere depuis plus de 24h."""

    _attr_translation_key = "patients_24h"
    _attr_icon = "mdi:account-clock"
    _attr_native_unit_of_measurement = "patients"

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._no_permis}_patients_24h"

    @property
    def native_value(self) -> int | None:
        inst = self._installation
        return inst.patients_24h if inst else None

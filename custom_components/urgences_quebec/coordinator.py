"""Coordinator - telecharge et parse le CSV horaire du MSSS."""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    COL_CIVIERES_FONCTIONNELLES,
    COL_CIVIERES_OCCUPEES,
    COL_DMS_AMBULATOIRE,
    COL_DMS_CIVIERE,
    COL_MISE_A_JOUR,
    COL_NO_PERMIS,
    COL_NOM_ETABLISSEMENT,
    COL_NOM_INSTALLATION,
    COL_PATIENTS_24H,
    COL_PATIENTS_48H,
    COL_PATIENTS_ATTENTE_PEC,
    COL_PATIENTS_TOTAL,
    COL_REGION,
    COL_RSS,
    CSV_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class InstallationData:
    """Donnees d'une installation (une urgence)."""

    no_permis: str
    nom_installation: str
    nom_etablissement: str
    region: str
    rss: str
    civieres_fonctionnelles: int | None
    civieres_occupees: int | None
    patients_24h: int | None
    patients_48h: int | None
    patients_total: int | None
    patients_attente_pec: int | None
    dms_civiere: float | None
    dms_ambulatoire: float | None


class UrgencesQuebecCoordinator(DataUpdateCoordinator[dict[str, InstallationData]]):
    """Coordinator - un fetch = toutes les installations du Quebec.

    Le filtrage par region/proximite/selection se fait cote entites,
    pas ici - ce coordinator garde toujours le jeu complet en memoire
    (petit fichier, ~137 lignes) pour permettre de changer les filtres
    via l'options flow sans reconfigurer le fetch.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.last_mise_a_jour: str | None = None

    async def _async_update_data(self) -> dict[str, InstallationData]:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(CSV_URL) as resp:
                resp.raise_for_status()
                # Verifie manuellement (2026-09-24, `file -i`) : source en
                # ISO-8859-1, pas UTF-8, malgre les caracteres accentues.
                raw = await resp.text(encoding="iso-8859-1")
        except Exception as err:  # noqa: BLE001 - remonte proprement a HA
            raise UpdateFailed(f"Echec telechargement CSV MSSS : {err}") from err

        return self._parse_csv(raw)

    def _parse_csv(self, raw: str) -> dict[str, InstallationData]:
        reader = csv.DictReader(io.StringIO(raw))
        # Bug reel trouve le 2026-09-24 : le CSV source du MSSS a des
        # tabulations/espaces parasites apres certains noms de colonnes
        # (ex. "Nombre_de_civieres_occupees\t\t\t\t      ,") - un lookup
        # exact sur le nom "propre" retourne toujours None pour ces
        # colonnes precises, causant une erreur silencieuse (division par
        # None) sur le taux d'occupation pour TOUTES les installations.
        # Fix robuste : normaliser les cles a chaque ligne plutot que de
        # dependre d'un nom de colonne exact, fragile a ce genre de bruit
        # si le gouvernement modifie a nouveau le format d'export.
        installations: dict[str, InstallationData] = {}
        mise_a_jour_vue: set[str] = set()

        for raw_row in reader:
            row = {(k or "").strip(): v for k, v in raw_row.items()}
            no_permis = (row.get(COL_NO_PERMIS) or "").strip()
            if not no_permis:
                continue

            mise_a_jour = (row.get(COL_MISE_A_JOUR) or "").strip()
            if mise_a_jour:
                mise_a_jour_vue.add(mise_a_jour)

            installations[no_permis] = InstallationData(
                no_permis=no_permis,
                nom_installation=(row.get(COL_NOM_INSTALLATION) or "").strip(),
                nom_etablissement=(row.get(COL_NOM_ETABLISSEMENT) or "").strip(),
                region=(row.get(COL_REGION) or "").strip(),
                rss=(row.get(COL_RSS) or "").strip(),
                civieres_fonctionnelles=_to_int(row.get(COL_CIVIERES_FONCTIONNELLES)),
                civieres_occupees=_to_int(row.get(COL_CIVIERES_OCCUPEES)),
                patients_24h=_to_int(row.get(COL_PATIENTS_24H)),
                patients_48h=_to_int(row.get(COL_PATIENTS_48H)),
                patients_total=_to_int(row.get(COL_PATIENTS_TOTAL)),
                patients_attente_pec=_to_int(row.get(COL_PATIENTS_ATTENTE_PEC)),
                dms_civiere=_to_float(row.get(COL_DMS_CIVIERE)),
                dms_ambulatoire=_to_float(row.get(COL_DMS_AMBULATOIRE)),
            )

        # Un seul horodatage attendu (voir PROGRESS.md - snapshot courant,
        # pas un historique). Si plusieurs valeurs distinctes apparaissent un
        # jour, l'hypothese "un seul snapshot par fichier" ne tient plus et
        # le parsing devra etre revu - on logue plutot que de planter.
        if len(mise_a_jour_vue) > 1:
            _LOGGER.warning(
                "Plusieurs horodatages Mise_a_jour distincts dans le meme "
                "fichier (%s) - hypothese de snapshot unique a revalider",
                mise_a_jour_vue,
            )
        if mise_a_jour_vue:
            nouveau = sorted(mise_a_jour_vue)[-1]
            if nouveau != self.last_mise_a_jour:
                _LOGGER.debug("Nouvelles donnees MSSS : %s", nouveau)
            self.last_mise_a_jour = nouveau

        return installations


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value or "pas d'information" in value.lower():
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value or "pas d'information" in value.lower():
        return None
    try:
        return float(value)
    except ValueError:
        return None

"""Constantes pour l'integration Urgences Quebec."""
from datetime import timedelta

DOMAIN = "urgences_quebec"

# Source verifiee manuellement le 2026-09-24 (voir PROGRESS.md) :
# 137 installations, une ligne par installation, colonne Mise_a_jour
# integree aux donnees (pas besoin de deviner la cadence de publication).
CSV_URL = (
    "https://www.msss.gouv.qc.ca/professionnels/statistiques/documents/"
    "urgences/Releve_horaire_urgences_7jours_nbpers.csv"
)

# Intervalle de depart "raisonnable" - a ajuster une fois le vrai pattern
# de publication du gouvernement confirme empiriquement (voir PROGRESS.md).
DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)

# Colonnes du CSV source (noms exacts, verifies sur un vrai telechargement)
COL_RSS = "RSS"
COL_REGION = "Region"
COL_NOM_ETABLISSEMENT = "Nom_etablissement"
COL_NOM_INSTALLATION = "Nom_installation"
COL_NO_PERMIS = "No_permis_installation"
COL_CIVIERES_FONCTIONNELLES = "Nombre_de_civieres_fonctionnelles"
COL_CIVIERES_OCCUPEES = "Nombre_de_civieres_occupees"
COL_PATIENTS_24H = "Nombre_de_patients_sur_civiere_plus_de_24_heures"
COL_PATIENTS_48H = "Nombre_de_patients_sur_civiere_plus_de_48_heures"
COL_PATIENTS_TOTAL = "Nombre_total_de_patients_presents_a_lurgence"
COL_PATIENTS_ATTENTE_PEC = "Nombre_total_de_patients_en_attente_de_PEC"
COL_DMS_CIVIERE = "DMS_sur_civiere"
COL_DMS_AMBULATOIRE = "DMS_ambulatoire"
COL_MISE_A_JOUR = "Mise_a_jour"

# Cles de configuration (config_flow / options_flow)
CONF_LOCATION = "location"
CONF_REGIONS = "regions"
CONF_NUM_NEAREST = "num_nearest"
CONF_INSTALLATIONS = "installations"
CONF_SHOW_DASHBOARD = "show_dashboard"
CONF_SELECT_ALL = "select_all"

# Panneau custom (dashboard optionnel, voir PROGRESS.md - pattern repris de
# config_map, API publique/stable panel_custom.async_register_panel)
URL_BASE = "/urgences_quebec_static"
PANEL_URL_PATH = "urgences-quebec"
PANEL_TITLE = "Urgences Québec"
PANEL_ICON = "mdi:hospital-box"
WEBCOMPONENT_NAME = "urgences-quebec-panel"

"""Helpers geographiques - chargement des coordonnees bundlees + distance."""
from __future__ import annotations

import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from homeassistant.core import HomeAssistant

DATA_PATH = Path(__file__).parent / "data" / "installations_geo.json"

RAYON_TERRE_KM = 6371.0


def _load_sync() -> dict[str, dict]:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


async def async_load_installations_geo(hass: HomeAssistant) -> dict[str, dict]:
    """Charge data/installations_geo.json (I/O bloquant -> executor)."""
    return await hass.async_add_executor_job(_load_sync)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance a vol d'oiseau entre 2 points (km)."""
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    return 2 * RAYON_TERRE_KM * asin(sqrt(a))

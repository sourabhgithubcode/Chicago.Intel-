"""CCA boundaries — Chicago Data Portal (Tier 3 pipeline, free, no key).

Source: data.cityofchicago.org/resource/igwz-8jzy (Community Area Boundaries).
GeoJSON endpoint — 77 features, one per community area.

After geometry is loaded, run these SQL steps to populate scores:
  1. assign_tracts_to_ccas()  -- sets tracts.cca_id via spatial join
  2. UPDATE ccas safety_score -- from cpd_incidents
  3. UPDATE ccas disp_score   -- from displacement_typology via tracts
  4. UPDATE ccas rent_median  -- population-weighted avg from tracts
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transformers.ccas import to_silver
from utils.bronze_store import write_bronze

GEOJSON_URL = "https://data.cityofchicago.org/resource/igwz-8jzy.geojson"


def fetch_all() -> list[dict]:
    r = requests.get(GEOJSON_URL, params={"$limit": 100}, timeout=30)
    r.raise_for_status()
    return r.json()["features"]


def run(run_id: str) -> list[dict]:
    raw = fetch_all()
    write_bronze("ccas", run_id, raw)
    return to_silver(raw)


if __name__ == "__main__":
    features = fetch_all()
    print(f"ccas: fetched {len(features)} community area boundaries")

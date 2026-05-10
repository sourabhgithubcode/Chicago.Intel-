"""API #9 — Chicago Park District (Tier 3 pipeline, ArcGIS Feature Service).

The Chicago Data Portal's parks datasets (ej32-qgdr, 5yyk-qt9y) currently
return empty JSON. The Park District's authoritative GIS layer lives on
ArcGIS Online instead — current boundaries with 614 features.

Source: services2.arcgis.com/dJOijx2lWTlGQBDJ/.../CW_414/FeatureServer/0
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transformers.parks import to_silver
from utils.bronze_store import write_bronze

LAYER = (
    "https://services2.arcgis.com/dJOijx2lWTlGQBDJ/arcgis/rest/services/"
    "CW_414/FeatureServer/0"
)
PAGE_SIZE = 1000  # ArcGIS default per-query cap


def fetch_all() -> list[dict]:
    """Page through the feature service, return raw GeoJSON features."""
    features: list[dict] = []
    offset = 0
    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
        }
        r = requests.get(f"{LAYER}/query", params=params, timeout=120)
        r.raise_for_status()
        page = r.json().get("features") or []
        if not page:
            break
        features.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return features


def run(run_id: str) -> list[dict]:
    raw = fetch_all()
    write_bronze("parks", run_id, raw)
    return to_silver(raw)


if __name__ == "__main__":
    print(f"parks: fetched {len(fetch_all())} features")

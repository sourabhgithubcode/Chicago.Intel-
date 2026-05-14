"""One-shot loader: Chicago tract polygons → tracts.geometry.

Source: Chicago Data Portal — Boundaries - Census Tracts - 2010 (74p9-q2aq).
GeoJSON has `geoid10` (11-digit Census tract GEOID) + Polygon/MultiPolygon
geometry. Upsert only {id, geometry} so any ACS-populated columns survive.

Run manually after applying migration 001 (or any time tracts.geometry is
NULL). No cron — tract boundaries change once per decennial census.
"""

import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from shapely.geometry import shape
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import Polygon

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from utils.bronze_store import write_bronze  # noqa: E402
from utils.supabase_admin import get_admin_client  # noqa: E402

URL = "https://data.cityofchicago.org/resource/74p9-q2aq.geojson"


def main() -> int:
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()
    features = resp.json().get("features", [])

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    write_bronze("tract_geometry", run_id, iter(features))

    rows = []
    for feat in features:
        geoid = (feat.get("properties") or {}).get("geoid10")
        geom_json = feat.get("geometry")
        if not geoid or not geom_json:
            continue
        try:
            geom = shape(geom_json)
        except Exception:
            continue
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        if not isinstance(geom, MultiPolygon) or geom.is_empty:
            continue
        rows.append({"id": geoid, "geometry": f"SRID=4326;{geom.wkt}"})

    get_admin_client().table("tracts").upsert(rows).execute()
    print(f"tracts: upserted geometry for {len(rows)} tracts")
    return 0


if __name__ == "__main__":
    sys.exit(main())

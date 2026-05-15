"""One-shot bronze archiver: Chicago Building Footprints → R2 only.

Source: data.cityofchicago.org syp8-uezg — ~820K MultiPolygon features.

Writes a single gzipped JSONL archive to R2 under
bronze/building_footprints/{run_id}.jsonl.gz. No Supabase silver write yet —
when a map UI section needs point-in-polygon lookups, add a migration +
silver-loader pass that reads this bronze file back.

Expect:
  - ~5–10 min download (17 pages of 50K rows)
  - ~150–250MB R2 upload
  - ~600MB peak Python memory (features held in RAM)
"""

import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from utils.bronze_store import write_bronze  # noqa: E402

BASE = "https://data.cityofchicago.org/resource/syp8-uezg.geojson"
PAGE = 50_000


def fetch_all():
    features = []
    offset = 0
    while True:
        url = f"{BASE}?$select=bldg_id,the_geom&$limit={PAGE}&$offset={offset}"
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        page = resp.json().get("features", [])
        if not page:
            break
        features.extend(page)
        print(f"  fetched {len(features):>7,} rows", flush=True)
        if len(page) < PAGE:
            break
        offset += PAGE
    return features


def main() -> int:
    features = fetch_all()

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    write_bronze("building_footprints", run_id, iter(features))

    rows = []
    for feat in features:
        bldg_id = (feat.get("properties") or {}).get("bldg_id")
        geom_json = feat.get("geometry")
        if not bldg_id or not geom_json:
            continue
        try:
            geom = shape(geom_json)
        except Exception:
            continue
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        if not isinstance(geom, MultiPolygon) or geom.is_empty:
            continue
        rows.append({
            "bldg_id": int(bldg_id),
            "geometry": f"SRID=4326;{geom.wkt}",
        })

    get_admin_client().table("building_footprints").upsert(rows).execute()
    print(f"building_footprints: upserted {len(rows)} footprints")
    return 0


if __name__ == "__main__":
    sys.exit(main())

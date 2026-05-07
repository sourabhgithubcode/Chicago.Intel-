"""CTA GTFS stops — bronze rows → silver rows for cta_stops table.

Source: transitchicago.com/developers/gtfs.aspx (stops.txt).
Confidence: 9/10 — official agency GTFS.

Silver schema (from supabase/migrations/001_create_tables.sql):
    cta_stops(id INT PK, name TEXT, lines TEXT[], accessible BOOL,
              location GEOMETRY(POINT, 4326))

Notes:
- GTFS stop_id is a stable integer in CTA's feed (range ~1–60013, unique).
  Using it as the PK lets re-runs upsert in place instead of clobbering rows.
- `lines` requires joining stop_times → trips → routes; left empty for V1.
  Backfill is a follow-up — see TODO in fetch_cta.py.
"""

from typing import Iterable

# Chicago bounding box — drops suburban stops that GTFS sometimes includes
# (Oak Park, Evanston, etc.). Matches CHI bbox used elsewhere in pipeline.
CHI_NORTH, CHI_SOUTH = 42.023, 41.644
CHI_EAST, CHI_WEST = -87.524, -87.940


def _in_chicago(lat: float, lng: float) -> bool:
    return CHI_SOUTH <= lat <= CHI_NORTH and CHI_WEST <= lng <= CHI_EAST


def to_silver(raw_rows: Iterable[dict]) -> list[dict]:
    """Map raw GTFS stops.txt rows to cta_stops silver rows."""
    silver = []
    seen_ids = set()
    for r in raw_rows:
        try:
            stop_id = int(r["stop_id"])
            lat = float(r["stop_lat"])
            lng = float(r["stop_lon"])
        except (KeyError, TypeError, ValueError):
            continue

        if stop_id in seen_ids:
            continue
        if not _in_chicago(lat, lng):
            continue

        seen_ids.add(stop_id)
        silver.append({
            "id": stop_id,
            "name": r["stop_name"],
            "lines": [],
            "accessible": r.get("wheelchair_boarding") == 1,
            "location": f"SRID=4326;POINT({lng} {lat})",
        })
    return silver

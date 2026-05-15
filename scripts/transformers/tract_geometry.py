"""Bronze → silver transformer for census tract geometries (GeoJSON).

Updates only the geometry column on existing tracts rows — other columns
are left untouched because we only include id + geometry in the upsert payload.
"""
from __future__ import annotations

from shapely.geometry import shape
from shapely.wkt import dumps


def to_silver(rows: list[dict]) -> list[dict]:
    silver: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        props = row.get("properties") or {}
        geom_json = row.get("geometry")

        geoid = str(props.get("geoid10", "")).strip()
        if not geoid or not geom_json or geoid in seen:
            continue
        seen.add(geoid)

        try:
            geom = shape(geom_json)
            if geom.is_empty:
                continue
            wkt = f"SRID=4326;{dumps(geom)}"
        except Exception:
            continue

        silver.append({"id": geoid, "geometry": wkt})
    return silver

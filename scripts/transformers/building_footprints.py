"""Bronze → silver transformer for Chicago building footprints (GeoJSON)."""
from __future__ import annotations

from shapely.geometry import shape
from shapely.wkt import dumps


def to_silver(rows: list[dict]) -> list[dict]:
    silver: list[dict] = []
    seen: set[int] = set()
    for row in rows:
        props = row.get("properties") or {}
        geom_json = row.get("geometry")

        try:
            bldg_id = int(props.get("bldg_id") or "")
        except (ValueError, TypeError):
            continue

        if bldg_id in seen or not geom_json:
            continue
        seen.add(bldg_id)

        try:
            geom = shape(geom_json)
            if geom.is_empty:
                continue
            wkt = f"SRID=4326;{dumps(geom)}"
        except Exception:
            continue

        silver.append({"bldg_id": bldg_id, "geometry": wkt})
    return silver

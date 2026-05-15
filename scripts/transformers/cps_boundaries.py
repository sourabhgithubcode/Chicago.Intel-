"""Bronze → silver transformer for CPS elementary school boundaries (GeoJSON)."""
from __future__ import annotations

from shapely.geometry import shape
from shapely.wkt import dumps


def to_silver(rows: list[dict]) -> list[dict]:
    silver: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        props = row.get("properties") or {}
        geom_json = row.get("geometry")

        school_id = str(props.get("school_id", "")).strip()
        if not school_id or school_id in seen:
            continue
        seen.add(school_id)

        boundary = None
        if geom_json:
            try:
                geom = shape(geom_json)
                if not geom.is_empty:
                    boundary = f"SRID=4326;{dumps(geom)}"
            except Exception:
                pass

        silver.append({
            "school_id":      school_id,
            "rcdts":          None,
            "school_name":    (props.get("short_name") or "").strip() or None,
            "grade_category": (props.get("grade_cat") or "").strip() or None,
            "school_year":    (props.get("boundarygr") or "").strip() or None,
            "boundary":       boundary,
        })
    return silver

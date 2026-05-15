"""Bronze → silver transformer for Chicago snow route restrictions (GeoJSON)."""
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
            obj_id = int(props.get("objectid") or "")
        except (ValueError, TypeError):
            continue

        on_street = (props.get("on_street") or "").strip()
        if not on_street or obj_id in seen or not geom_json:
            continue
        seen.add(obj_id)

        try:
            geom = shape(geom_json)
            if geom.is_empty:
                continue
            wkt = f"SRID=4326;{dumps(geom)}"
        except Exception:
            continue

        silver.append({
            "id":               obj_id,
            "on_street":        on_street,
            "from_street":      (props.get("from_stree") or "").strip() or None,
            "to_street":        (props.get("to_street") or "").strip() or None,
            "restriction_type": (props.get("restrict_t") or "").strip() or None,
            "geometry":         wkt,
        })
    return silver

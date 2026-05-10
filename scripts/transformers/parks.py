"""Park District boundaries — ArcGIS GeoJSON features → silver rows for parks.

Source: services2.arcgis.com/dJOijx2lWTlGQBDJ/.../CW_414/FeatureServer/0
        (Chicago Park District Park Boundaries — current, ~614 features).
Confidence: 9/10 — Park District authoritative boundaries.

Silver schema (migration 001):
    parks(id INT PK, name TEXT NOT NULL, acreage NUMERIC(8,2),
          location GEOMETRY(POINT, 4326),
          boundary GEOMETRY(MULTIPOLYGON, 4326))

`location` is the polygon centroid — `parks.location` is a POINT but
boundary polygons are the source-of-truth shape. Centroid gives the
single-point representation needed for nearest-park lookups.
"""
from __future__ import annotations

from typing import Iterable

from shapely.geometry import shape
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import Polygon


def to_silver(features: Iterable[dict]) -> list[dict]:
    silver = []
    seen = set()
    for feat in features:
        props = feat.get("properties") or {}
        try:
            park_id = int(props["park_no"])
        except (KeyError, TypeError, ValueError):
            continue
        if park_id in seen:
            continue
        name = props.get("label") or props.get("park")
        if not name:
            continue

        geom_json = feat.get("geometry")
        if not geom_json:
            continue
        try:
            geom = shape(geom_json)
        except Exception:
            continue
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        if not isinstance(geom, MultiPolygon) or geom.is_empty:
            continue

        centroid = geom.centroid
        seen.add(park_id)
        silver.append({
            "id": park_id,
            "name": name,
            "acreage": props.get("acres"),
            "location": f"SRID=4326;POINT({centroid.x} {centroid.y})",
            "boundary": f"SRID=4326;{geom.wkt}",
        })
    return silver

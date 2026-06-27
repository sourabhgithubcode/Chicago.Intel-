"""CCA geometry — GeoJSON features → silver rows for ccas.

Source: data.cityofchicago.org/resource/igwz-8jzy (Community Area Boundaries).
Maps area_numbe (1–77) → ccas.id. Geometry only; scores are computed
from silver tables after load (see fetch_ccas.py).
"""
from __future__ import annotations

from typing import Iterable


def to_silver(raw_rows: Iterable[dict]) -> list[dict]:
    """Map GeoJSON features to ccas silver rows (id + geometry only)."""
    silver = []
    for feat in raw_rows:
        props = feat.get("properties", {})
        geom = feat.get("geometry")
        if not geom or not props.get("area_numbe"):
            continue
        try:
            cca_id = int(props["area_numbe"])
        except (TypeError, ValueError):
            continue
        if not 1 <= cca_id <= 77:
            continue
        silver.append({
            "id": cca_id,
            "name": props.get("community", "").title(),
            "geometry": f"SRID=4326;{_multipolygon_wkt(geom['coordinates'])}",
        })
    return silver


def _multipolygon_wkt(coords) -> str:
    polys = []
    for poly in coords:
        rings = []
        for ring in poly:
            pts = ",".join(f"{x} {y}" for x, y in ring)
            rings.append(f"({pts})")
        polys.append(f"({','.join(rings)})")
    return f"MULTIPOLYGON({','.join(polys)})"

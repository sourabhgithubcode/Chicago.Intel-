"""CPD crime incidents — bronze rows → silver rows for cpd_incidents.

Source: data.cityofchicago.org/resource/ijzp-q8t2 (Crimes 2001-present).
Confidence: 7/10 — official CPD reports, but unfounded/reclassified incidents
remain in the feed; we don't filter them.

Silver schema (migration 001):
    cpd_incidents(id BIGINT PK, iucr TEXT, type TEXT CHECK IN
                  ('violent','property','other'), description TEXT,
                  date DATE NOT NULL, location GEOMETRY(POINT, 4326))

The `type` CHECK constraint forces every row into violent/property/other.
The IUCR_TYPE map below covers the FBI Part 1 violent + property codes; any
other IUCR falls into 'other'. Source: CPD IUCR code reference.
"""
from __future__ import annotations

from typing import Iterable

# Chicago bbox — matches the in_chicago_bbox() CHECK in migration 013.
# Some CPD records have garbage coords (e.g. far-west outliers).
_CHI_W, _CHI_E = -87.940, -87.524
_CHI_S, _CHI_N = 41.644, 42.023

# FBI Part 1 violent (homicide, criminal sexual assault, robbery, agg assault/battery)
_VIOLENT_PREFIXES = ("01", "02", "03", "04")
# FBI Part 1 property (burglary, theft, MVT, arson)
_PROPERTY_PREFIXES = ("05", "06", "07", "09")


def _classify(iucr: str) -> str:
    """Return 'violent' / 'property' / 'other' for a CPD IUCR code."""
    if not iucr:
        return "other"
    head = iucr[:2]
    if head in _VIOLENT_PREFIXES:
        return "violent"
    if head in _PROPERTY_PREFIXES:
        return "property"
    return "other"


def to_silver(raw_rows: Iterable[dict]) -> list[dict]:
    """Map raw CPD Socrata rows to cpd_incidents silver rows."""
    silver = []
    seen = set()
    for r in raw_rows:
        try:
            row_id = int(r["id"])
            lat = float(r["latitude"])
            lng = float(r["longitude"])
            date = r["date"][:10]  # 'YYYY-MM-DDTHH:MM:SS' → 'YYYY-MM-DD'
        except (KeyError, TypeError, ValueError):
            continue
        if not (_CHI_W <= lng <= _CHI_E and _CHI_S <= lat <= _CHI_N):
            continue
        if row_id in seen:
            continue
        seen.add(row_id)

        iucr = r.get("iucr", "") or ""
        silver.append({
            "id": row_id,
            "iucr": iucr,
            "type": _classify(iucr),
            "description": r.get("description"),
            "date": date,
            "location": f"SRID=4326;POINT({lng} {lat})",
        })
    return silver

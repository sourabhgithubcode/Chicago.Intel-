"""311 service requests — bronze rows → silver rows for complaints_311.

Source: data.cityofchicago.org/resource/v6vf-nfxy (311 Service Requests).
Confidence: 9/10 — official 311 system of record.

Silver schema (migration 001):
    complaints_311(id BIGINT PK, type TEXT, address TEXT, date DATE,
                   location GEOMETRY(POINT, 4326))

`sr_number` is text (e.g. 'SR19-01802317'). We strip 'SR' and '-' to get a
stable bigint (e.g. 1901802317), which fits the silver PK and re-runs upsert
in place.
"""
from __future__ import annotations

from typing import Iterable

# Chicago bbox — matches in_chicago_bbox() CHECK in migration 013.
_CHI_W, _CHI_E = -87.940, -87.524
_CHI_S, _CHI_N = 41.644, 42.023


def _parse_id(sr_number: str) -> int | None:
    s = sr_number.replace("SR", "").replace("-", "")
    return int(s) if s.isdigit() else None


def to_silver(raw_rows: Iterable[dict]) -> list[dict]:
    silver = []
    seen = set()
    for r in raw_rows:
        sr = r.get("sr_number")
        if not sr:
            continue
        row_id = _parse_id(sr)
        if row_id is None or row_id in seen:
            continue
        seen.add(row_id)

        try:
            lat = float(r["latitude"])
            lng = float(r["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (_CHI_W <= lng <= _CHI_E and _CHI_S <= lat <= _CHI_N):
            continue

        created = r.get("created_date") or ""
        if len(created) < 10:
            continue

        silver.append({
            "id": row_id,
            "type": r.get("sr_type"),
            "address": r.get("street_address"),
            "date": created[:10],
            "location": f"SRID=4326;POINT({lng} {lat})",
        })
    return silver

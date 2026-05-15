"""Bronze → silver transformer for Chicago building permits (Socrata)."""
from __future__ import annotations

from datetime import datetime

_BBOX = dict(W=-87.940, E=-87.524, S=41.644, N=42.023)

_CATEGORY = [
    ("new_construction", ["NEW CONSTRUCTION"]),
    ("renovation",       ["RENOVATION", "ALTERATION", "REPAIR", "REHAB"]),
    ("demolition",       ["WRECK", "DEMOLITION"]),
]


def _cat(permit_type: str) -> str:
    pt = (permit_type or "").upper()
    for cat, kws in _CATEGORY:
        if any(k in pt for k in kws):
            return cat
    return "other"


def _ts(val: str | None) -> str | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val[:19]).isoformat()
    except (ValueError, TypeError):
        return None


def to_silver(rows: list[dict]) -> list[dict]:
    silver: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        row_id = str(row.get("id", "")).strip()
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)

        parts = [row.get("street_number", ""), row.get("street_direction", ""),
                 row.get("street_name", "")]
        address = " ".join(p.strip() for p in parts if p and p.strip()) or None
        address_norm = " ".join(address.upper().split()) if address else None

        location = None
        try:
            lat = float(row.get("latitude") or "")
            lng = float(row.get("longitude") or "")
            if (_BBOX["S"] <= lat <= _BBOX["N"] and _BBOX["W"] <= lng <= _BBOX["E"]):
                location = f"SRID=4326;POINT({lng} {lat})"
        except (ValueError, TypeError):
            pass

        reported_cost = None
        try:
            rc = row.get("reported_cost")
            if rc is not None:
                reported_cost = int(float(rc))
        except (ValueError, TypeError):
            pass

        permit_fee = None
        try:
            tf = row.get("total_fee")
            if tf is not None:
                permit_fee = float(tf)
        except (ValueError, TypeError):
            pass

        silver.append({
            "id":            row_id,
            "permit_type":   (row.get("permit_type") or "").strip() or None,
            "category":      _cat(row.get("permit_type", "")),
            "issue_date":    _ts(row.get("issue_date")),
            "applied_at":    _ts(row.get("application_start_date")),
            "pin":           None,
            "address":       address,
            "address_norm":  address_norm,
            "reported_cost": reported_cost,
            "permit_fee":    permit_fee,
            "location":      location,
        })
    return silver

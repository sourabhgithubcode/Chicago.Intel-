"""CPD crime incidents — bronze rows → silver rows for cpd_incidents.

Source: data.cityofchicago.org/resource/ijzp-q8t2 (Crimes 2001-present).
Confidence: 7/10 — official CPD reports, but unfounded/reclassified incidents
remain in the feed; we don't filter them.

Silver schema (migrations 001 + 014):
    cpd_incidents(id BIGINT PK, iucr TEXT, type TEXT CHECK IN
                  ('violent','property','other'),
                  date DATE NOT NULL, location GEOMETRY(POINT, 4326))

`description` was dropped in 014 — IUCR is the canonical 4-char code, and
Chicago publishes the IUCR→description lookup separately.

The `type` CHECK constraint forces every row into violent/property/other.
`classify_iucr()` below maps each exact IUCR code to its FBI Part 1 class using
the official Chicago IUCR dictionary (c7ck-438e, index_code='I'); everything
else is 'other'.
"""
from __future__ import annotations

from typing import Iterable

# Chicago bbox — matches the in_chicago_bbox() CHECK in migration 013.
# Some CPD records have garbage coords (e.g. far-west outliers).
_CHI_W, _CHI_E = -87.940, -87.524
_CHI_S, _CHI_N = 41.644, 42.023

# FBI Part 1 (index) violent vs property classification, by EXACT IUCR code.
#
# The 2-char IUCR prefix is NOT a reliable index of crime class — prefix 08 is
# THEFT (property) and prefix 05 is aggravated ASSAULT (violent). The old
# `iucr[:2]` heuristic therefore dropped ~21% of all crime (theft) to "other"
# and filed aggravated assault as "property". These sets are the exact codes
# where the official Chicago IUCR dictionary
# (data.cityofchicago.org/resource/c7ck-438e) has index_code = 'I' (Part 1),
# grouped by primary_description:
#   violent  = HOMICIDE, CRIMINAL SEXUAL ASSAULT, ROBBERY, ASSAULT, BATTERY
#   property = BURGLARY, THEFT, MOTOR VEHICLE THEFT, ARSON
# Non-index codes (simple assault/battery) and non-Part-1 index crimes
# (human trafficking, offenses involving children) fall through to "other".
_VIOLENT_IUCR = frozenset({
    "0110", "0130",                                              # homicide
    "0261", "0262", "0263", "0264", "0265", "0266", "0271",      # criminal sexual assault
    "0272", "0273", "0274", "0275", "0281", "0291",
    "0312", "0313", "031A", "031B", "0320", "0325", "0326",      # robbery
    "0330", "0331", "0334", "0337", "033A", "033B", "0340",
    "041A", "041B", "0420", "0430", "0450", "0451", "0452",      # battery (aggravated)
    "0453", "0461", "0462", "0479", "0480", "0481", "0482",
    "0483", "0485", "0487", "0488", "0489", "0495", "0496",
    "0497", "0498", "0499",
    "051A", "051B", "0520", "0530", "0550", "0551", "0552",      # assault (aggravated)
    "0553", "0555", "0556", "0557", "0558",
})
_PROPERTY_IUCR = frozenset({
    "0610", "0620", "0630", "0650", "0710", "0760",              # burglary
    "0810", "0820", "0830", "0840", "0841", "0842", "0843",      # theft
    "0850", "0860", "0865", "0870", "0880", "0890", "0895",
    "0910", "0915", "0917", "0918", "0920", "0925", "0927",      # motor vehicle theft
    "0928", "0930", "0935", "0937", "0938",
    "1010", "1020", "1025", "1090",                              # arson
})


def classify_iucr(iucr: str) -> str:
    """Return 'violent' / 'property' / 'other' for a CPD IUCR code.

    Shared with scripts/scoring/safety.py so the safety score and the silver
    `type` column use one authoritative classification.
    """
    if not iucr:
        return "other"
    if iucr in _VIOLENT_IUCR:
        return "violent"
    if iucr in _PROPERTY_IUCR:
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
            "type": classify_iucr(iucr),
            "date": date,
            "location": f"SRID=4326;POINT({lng} {lat})",
        })
    return silver

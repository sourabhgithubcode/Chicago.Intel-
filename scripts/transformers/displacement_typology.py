"""Bronze → silver transformer for DePaul IHS displacement typology data."""
from __future__ import annotations


def to_silver(rows: list[dict]) -> list[dict]:
    silver: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        inner = row.get("row") or {}
        geoid = str(inner.get("GEOID", "")).strip()
        typology = str(inner.get("Typology", "")).strip()
        if not geoid or not typology or geoid in seen:
            continue
        seen.add(geoid)
        silver.append({"geoid": geoid, "typology": typology})
    return silver

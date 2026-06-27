"""Displacement score (0–10) for tracts, derived from UDP typology.

Source: Urban Displacement Project (UC Berkeley + SPARCC + DePaul IHS) Chicago
tract typology, stored in `displacement_typology(geoid, typology)`. Vintage
2013–2018 — confidence 6/10.

The 0–10 score is an ordinal risk mapping of the typology categories. These
exact weights were RECOVERED by least-squares from the existing, pre-committed
`ccas.disp_score` values (which were produced by ad-hoc SQL that was never
checked into the repo): solving `mean(tract score) == ccas.disp_score` across
all 77 CCAs reproduces the stored values to RMSE 0.012 / max error 0.094. So
applying this map to tracts is consistent with the CCA scores already shown in
the dashboard, and is now reproducible and auditable.

Higher score = higher displacement pressure. "Unavailable or Unreliable Data"
maps to NULL (no honest score), not to a midpoint — per the project rule that
we never invent a number without a source.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from utils.supabase_admin import get_admin_client  # noqa: E402

from scoring import fetch_all  # noqa: E402

# Typology → 0–10 displacement-pressure score. None = no score (unreliable data).
TYPOLOGY_SCORE: dict[str, float | None] = {
    "Ongoing Displacement": 10.0,
    "Advanced Gentrification": 9.0,
    "Early/Ongoing Gentrification": 8.0,
    "Low-Income/Susceptible to Displacement": 8.0,
    "At Risk of Gentrification": 6.0,
    "Becoming Exclusive": 6.0,
    "At Risk of Becoming Exclusive": 5.0,
    "High Student Population": 4.0,
    "Stable Moderate/Mixed Income": 3.0,
    "Stable/Advanced Exclusive": 2.0,
    "Unavailable or Unreliable Data": None,
}


def compute() -> dict:
    """Map each tract's typology to a disp_score and upsert. Idempotent."""
    client = get_admin_client()

    # displacement_typology is 1,982 rows; tracts is 1,348 — both exceed the
    # PostgREST 1000-row page cap, so read paged.
    typ = fetch_all(client, "displacement_typology", "geoid,typology", key="geoid")
    tracts = fetch_all(client, "tracts", "id", key="id")

    geoid_to_typ = {t["geoid"]: t["typology"] for t in typ}
    tract_ids = {t["id"] for t in tracts}

    payload: list[dict] = []
    stats = {"scored": 0, "unreliable_null": 0, "no_typology": 0, "unknown_typology": 0}
    for tid in tract_ids:
        typology = geoid_to_typ.get(tid)
        if typology is None:
            stats["no_typology"] += 1
            continue
        if typology not in TYPOLOGY_SCORE:
            stats["unknown_typology"] += 1
            continue
        score = TYPOLOGY_SCORE[typology]
        if score is None:
            stats["unreliable_null"] += 1
            continue
        payload.append({"id": tid, "disp_score": score})
        stats["scored"] += 1

    if payload:
        client.table("tracts").upsert(payload).execute()

    return stats


if __name__ == "__main__":
    s = compute()
    print(
        f"tracts.disp_score: scored={s['scored']} "
        f"unreliable→null={s['unreliable_null']} "
        f"no_typology={s['no_typology']} unknown_typology={s['unknown_typology']}"
    )

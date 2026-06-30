"""Roll tract-level ACS inputs up to CCAs (population-weighted).

The 77-CCA affordability engine reads its inputs at CCA grain, but several ACS
variables live only on `tracts` (income, vacancy, tenure, poverty, transit share,
autos/household). This module aggregates them to each CCA by population-weighted
mean and upserts the CCA input columns. The affordability + vulnerability scorers
then read those CCA columns directly (no repeated spatial joins).

Tract→CCA mapping uses a centroid-in-CCA-polygon spatial join — the same approach
as scoring/safety.py — because `tracts.cca_id` is only ~58% populated.

Inputs (tracts) → outputs (ccas), pop-weighted:
    income_median, vacancy_rate, renter_occupied_pct, poverty_rate,
    transit_share, autos_per_hh

Run: `.venv/bin/python scripts/scoring/acs_rollup.py`
(depends on migration 030 columns + a fetch_acs run that populated the three new
tract columns poverty_rate / transit_share / autos_per_hh).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import geopandas as gpd  # noqa: E402
from shapely.geometry import shape  # noqa: E402

from utils.supabase_admin import get_admin_client  # noqa: E402
from scoring import fetch_all  # noqa: E402

# col -> rounding (income is an INT; rates 3dp; autos 2dp)
COLS = {
    "income_median": 0,
    "vacancy_rate": 3,
    "renter_occupied_pct": 3,
    "poverty_rate": 3,
    "transit_share": 3,
    "autos_per_hh": 2,
}


def _wmean(rows: list[dict], col: str, ndigits: int):
    """Population-weighted mean of `col` over rows, skipping null value/pop."""
    num = den = 0.0
    for r in rows:
        v, p = r.get(col), r.get("population")
        if v is None or p is None or p <= 0:
            continue
        num += p * float(v)
        den += p
    if den <= 0:
        return None
    m = round(num / den, ndigits)
    return int(m) if ndigits == 0 else m


def compute() -> dict:
    client = get_admin_client()

    ccas = fetch_all(client, "ccas", "id,name,geometry", {"geometry": "not.is.null"})
    tracts = fetch_all(client, "tracts",
                       "id,population,geometry," + ",".join(COLS),
                       {"geometry": "not.is.null"}, key="id")

    cca_name = {c["id"]: c["name"] for c in ccas}
    cca_gdf = gpd.GeoDataFrame(
        [{"cca_id": c["id"]} for c in ccas],
        geometry=[shape(c["geometry"]) for c in ccas], crs=4326)
    tr_gdf = gpd.GeoDataFrame(
        [{"i": i} for i in range(len(tracts))],
        geometry=[shape(t["geometry"]) for t in tracts], crs=4326)
    tr_gdf["geometry"] = tr_gdf.geometry.representative_point()

    joined = gpd.sjoin(tr_gdf, cca_gdf, predicate="within", how="inner")

    payload = []
    for cid, sub in joined.groupby("cca_id"):
        rows = [tracts[i] for i in sub["i"]]
        row = {"id": cid, "name": cca_name[cid]}  # ccas.name is NOT NULL
        for col, nd in COLS.items():
            row[col] = _wmean(rows, col, nd)
        payload.append(row)

    for i in range(0, len(payload), 400):
        client.table("ccas").upsert(payload[i:i + 400]).execute()

    return {"ccas_rolled_up": len(payload), "tracts_used": len(joined)}


if __name__ == "__main__":
    s = compute()
    print(f"acs_rollup: ccas={s['ccas_rolled_up']} tracts_used={s['tracts_used']}")

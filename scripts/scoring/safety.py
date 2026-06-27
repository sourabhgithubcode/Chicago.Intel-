"""Safety score (0–10) for CCAs and tracts — per-capita CPD crime rate.

Documented, reproducible methodology that REPLACES the prior ad-hoc CCA SQL
(which was never committed and used raw crime *counts*):

    weighted = property_5yr + VIOLENT_WEIGHT * violent_5yr   # severity weighting
    rate     = weighted / population * 1000                  # per 1,000 residents
    safety   = clamp(10 - rate / RATE_AT_ZERO * 10, 0, 10)   # higher = safer

- Window: CPD incidents (type violent/property) over the last LOOKBACK_YEARS.
- VIOLENT_WEIGHT = 3 was recovered by least-squares from the prior CCA scores
  (RMSE 0.07) — i.e. the original authors weighted violent crime ~3x property.
- RATE_AT_ZERO = 1100 weighted 5-yr crimes per 1,000 residents → safety 0. This
  is the ~98th percentile of the observed CCA+tract rate distribution, FIXED as a
  constant so a score only moves when that area's own crime rate moves, not when
  another area changes (stability = trust).
- Per-capita normalization fixes the prior raw-count bias: low-population /
  high-rate areas (e.g. Fuller Park) scored ~9 "safe" under raw counts but are
  ~0 per-capita. Confidence 7/10 (CPD IUCR).
- Caveat ("what this does not tell you"): residential-population basis understates
  safety in low-residential / high-daytime-traffic areas (Near South Side, Loop).

Run: `.venv/bin/python scripts/scoring/safety.py` (pulls ~540k crime points +
spatial-joins — takes a few minutes).
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import geopandas as gpd  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402

from utils.supabase_admin import get_admin_client  # noqa: E402
from scoring import fetch_all  # noqa: E402
from transformers.cpd import classify_iucr  # noqa: E402

VIOLENT_WEIGHT = 3
RATE_AT_ZERO = 1100.0  # weighted 5-yr crimes per 1,000 residents → safety 0
LOOKBACK_YEARS = 5


def _safety(weighted: float, population: float | None) -> float | None:
    if not population or population <= 0:
        return None
    rate = weighted / population * 1000.0
    return round(max(0.0, min(10.0, 10.0 - rate / RATE_AT_ZERO * 10.0)), 2)


def compute() -> dict:
    client = get_admin_client()
    window = (date.today() - timedelta(days=365 * LOOKBACK_YEARS)).isoformat()

    # Polygons + population
    ccas = fetch_all(client, "ccas", "id,name,geometry")
    tracts = fetch_all(client, "tracts", "id,population,geometry",
                       {"geometry": "not.is.null"})
    cca_name = {c["id"]: c["name"] for c in ccas}
    cca_gdf = gpd.GeoDataFrame(
        [{"cca_id": c["id"]} for c in ccas],
        geometry=[shape(c["geometry"]) for c in ccas], crs=4326)
    tr_gdf = gpd.GeoDataFrame(
        [{"tract_id": t["id"], "population": t["population"]} for t in tracts],
        geometry=[shape(t["geometry"]) for t in tracts], crs=4326)

    # Crime points, last 5 years. Classify from IUCR here (the silver `type`
    # column is mis-bucketed — see transformers/cpd.classify_iucr); keep only
    # the Part 1 violent/property index crimes the score weights.
    raw = fetch_all(client, "cpd_incidents", "id,iucr,location",
                    {"date": f"gte.{window}"}, key="id")
    crimes = [{"type": t, "location": c["location"]}
              for c in raw for t in (classify_iucr(c.get("iucr") or ""),)
              if t != "other"]
    pt_gdf = gpd.GeoDataFrame(
        {"type": [c["type"] for c in crimes]},
        geometry=[Point(*c["location"]["coordinates"]) for c in crimes], crs=4326)

    def weighted_counts(poly_gdf, key):
        j = gpd.sjoin(pt_gdf, poly_gdf, predicate="within", how="inner")
        out = {}
        for k, sub in j.groupby(key):
            v = int((sub["type"] == "violent").sum())
            p = int((sub["type"] == "property").sum())
            out[k] = p + VIOLENT_WEIGHT * v
        return out

    tr_weighted = weighted_counts(tr_gdf, "tract_id")
    cca_weighted = weighted_counts(cca_gdf, "cca_id")

    # CCA residential population = sum of tract populations whose centroid is in the CCA
    cent = tr_gdf.copy()
    cent["geometry"] = tr_gdf.geometry.representative_point()
    cca_pop = (gpd.sjoin(cent, cca_gdf, predicate="within", how="inner")
               .groupby("cca_id")["population"].sum().to_dict())

    # Build upserts
    tr_payload, cca_payload = [], []
    tr_pop = {t["tract_id"]: t["population"] for t in
              tr_gdf[["tract_id", "population"]].to_dict("records")}
    for tid in tr_pop:
        s = _safety(tr_weighted.get(tid, 0), tr_pop.get(tid))
        if s is not None:
            tr_payload.append({"id": tid, "safety_score": s})
    for cid in [c["id"] for c in ccas]:
        s = _safety(cca_weighted.get(cid, 0), cca_pop.get(cid))
        if s is not None:
            # include name: ccas.name is NOT NULL, required on upsert's insert tuple
            cca_payload.append({"id": cid, "name": cca_name[cid], "safety_score": s})

    if tr_payload:
        client.table("tracts").upsert(tr_payload).execute()
    if cca_payload:
        client.table("ccas").upsert(cca_payload).execute()

    return {"window": window, "crimes": len(crimes),
            "ccas_scored": len(cca_payload), "tracts_scored": len(tr_payload)}


if __name__ == "__main__":
    s = compute()
    print(f"safety: window>={s['window']} crimes={s['crimes']} "
          f"ccas_scored={s['ccas_scored']} tracts_scored={s['tracts_scored']}")

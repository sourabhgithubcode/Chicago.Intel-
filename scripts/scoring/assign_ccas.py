"""Assign tracts.cca_id from geometry — the reproducible `assign_tracts_to_ccas`.

fetch_ccas.py's docstring lists "assign_tracts_to_ccas()  -- sets tracts.cca_id
via spatial join" as the first post-load step, but no such function was ever
committed (it was one-off ad-hoc SQL). That left boundary tracts NULL: a strict
point-in-polygon join misses edge tracts (O'Hare, Hegewisch, lakefront) whose
representative point sits just outside every CCA polygon, so they show blank in
the breadcrumb/choropleth. This module makes the step reproducible:

    cca_id = CCA polygon CONTAINING the tract's representative point (ST_Within);
             if none contains it, the NEAREST CCA polygon (boundary fallback).

Only tracts WITH geometry can be assigned. The whole-Cook-County ACS pull
(fetch_acs.py) creates tract rows outside the City of Chicago that have no
Chicago tract polygon and belong to no community area; those correctly keep
cca_id NULL (they are out of scope for a Chicago dashboard).

Run AFTER tract geometry + CCA geometry are loaded:
    `.venv/bin/python scripts/scoring/assign_ccas.py`
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


def compute() -> dict:
    client = get_admin_client()

    ccas = fetch_all(client, "ccas", "id,geometry", {"geometry": "not.is.null"})
    tracts = fetch_all(client, "tracts", "id,geometry",
                       {"geometry": "not.is.null"}, key="id")

    cca_gdf = gpd.GeoDataFrame(
        [{"cca_id": c["id"]} for c in ccas],
        geometry=[shape(c["geometry"]) for c in ccas], crs=4326)
    tr_gdf = gpd.GeoDataFrame(
        [{"tract_id": t["id"]} for t in tracts],
        geometry=[shape(t["geometry"]) for t in tracts], crs=4326)
    tr_gdf["geometry"] = tr_gdf.geometry.representative_point()  # a point ON the tract

    within = gpd.sjoin(tr_gdf, cca_gdf, predicate="within", how="left")
    within = within[~within.index.duplicated(keep="first")]

    assigned: dict[str, int] = {}
    unresolved = []
    for idx, row in within.iterrows():
        cid = row.get("cca_id")
        if cid is not None and cid == cid:  # not NaN
            assigned[row["tract_id"]] = int(cid)
        else:
            unresolved.append(idx)

    # Boundary fallback: nearest CCA polygon (projected metres) when the tract's
    # representative point fell outside every CCA polygon.
    if unresolved:
        cca_m = cca_gdf.to_crs(26971)
        pts_m = tr_gdf.loc[unresolved].to_crs(26971)
        nearest = gpd.sjoin_nearest(pts_m, cca_m, how="left")
        nearest = nearest[~nearest.index.duplicated(keep="first")]
        for idx, row in nearest.iterrows():
            assigned[tr_gdf.loc[idx, "tract_id"]] = int(row["cca_id"])

    payload = [{"id": tid, "cca_id": cid} for tid, cid in assigned.items()]
    for i in range(0, len(payload), 400):
        client.table("tracts").upsert(payload[i:i + 400]).execute()

    return {"tracts_with_geometry": len(tracts), "assigned": len(payload)}


if __name__ == "__main__":
    s = compute()
    print(f"assign_ccas: tracts_with_geometry={s['tracts_with_geometry']} "
          f"assigned={s['assigned']}")

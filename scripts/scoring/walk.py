"""Walk score (0–10) for CCAs and tracts — transit + park access density.

A SIGNAL, not a measurement (confidence 6/10). The proprietary Walk Score® is
licensed and amenity-based; this is an open-data proxy from the two walkability
inputs we have loaded:

    transit = CTA stops within the area / area_km2      (stops per km²)
    parks   = Park District parks within the area / area_km2
    walk = clamp( min(transit/TRANSIT_FULL, 1)*8 + min(parks/PARK_FULL, 1)*2, 0, 10)

Transit dominates (80%) because CTA stop density discriminates Chicago
walkability well (Loop ~46 stops/km² → high; O'Hare/Hegewisch <4 → low). Parks
add a 20% access bonus. TRANSIT_FULL / PARK_FULL are FIXED (≈ the observed top
of each distribution) so a score only moves when that area's own access changes.

Caveat ("what this does not tell you"): excludes destination/amenity density,
pedestrian infrastructure, intersection density, and block length — so it
under-credits dense retail strips and over-credits bus-blanketed low-density areas.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import geopandas as gpd  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402

from utils.supabase_admin import get_admin_client  # noqa: E402
from scoring import fetch_all  # noqa: E402

TRANSIT_FULL = 40.0  # CTA stops per km² for full transit credit (~Loop level)
PARK_FULL = 3.0      # parks per km² for full park credit


def _walk(transit_density: float, park_density: float) -> float:
    t = min(transit_density / TRANSIT_FULL, 1.0) * 8.0
    p = min(park_density / PARK_FULL, 1.0) * 2.0
    return round(max(0.0, min(10.0, t + p)), 2)


def _counts(points_gdf, poly_gdf, key):
    j = gpd.sjoin(points_gdf, poly_gdf[["geometry", key]], predicate="within", how="inner")
    return j.groupby(key).size().to_dict()


def compute() -> dict:
    client = get_admin_client()

    ccas = fetch_all(client, "ccas", "id,name,geometry", key="id")
    tracts = fetch_all(client, "tracts", "id,geometry", {"geometry": "not.is.null"}, key="id")
    cta = fetch_all(client, "cta_stops", "id,location", key="id")
    parks = fetch_all(client, "parks", "id,location", key="id")

    cta_pts = gpd.GeoDataFrame(
        geometry=[Point(*s["location"]["coordinates"]) for s in cta], crs=4326)
    park_pts = gpd.GeoDataFrame(
        geometry=[Point(*p["location"]["coordinates"]) for p in parks], crs=4326)

    def score_polys(rows, key, name_map=None):
        gdf = gpd.GeoDataFrame([{key: r[key]} for r in rows],
                               geometry=[shape(r["geometry"]) for r in rows], crs=4326)
        gdf["area_km2"] = gdf.to_crs(26971).geometry.area / 1e6
        cta_n = _counts(cta_pts, gdf, key)
        park_n = _counts(park_pts, gdf, key)
        out = []
        for r in gdf.itertuples():
            k = getattr(r, key)
            if not r.area_km2 or r.area_km2 <= 0:
                continue
            w = _walk(cta_n.get(k, 0) / r.area_km2, park_n.get(k, 0) / r.area_km2)
            row = {key: k, "walk_score": w}
            if name_map is not None:
                row["name"] = name_map[k]  # ccas.name is NOT NULL
            out.append(row)
        return out

    cca_payload = score_polys(ccas, "id", {c["id"]: c["name"] for c in ccas})
    tract_payload = score_polys(tracts, "id")

    for i in range(0, len(cca_payload), 400):
        client.table("ccas").upsert(cca_payload[i:i + 400]).execute()
    for i in range(0, len(tract_payload), 400):
        client.table("tracts").upsert(tract_payload[i:i + 400]).execute()

    return {"ccas_scored": len(cca_payload), "tracts_scored": len(tract_payload)}


if __name__ == "__main__":
    s = compute()
    print(f"walk: ccas_scored={s['ccas_scored']} tracts_scored={s['tracts_scored']}")

"""Lifestyle sub-scores (0–10) per CCA from OpenStreetMap — vibe, bike, run.

Free Overpass data (no API key; MUST send a User-Agent — Overpass blocks the
default python-requests UA). Each metric is a density on a FIXED anchor (a CCA's
score only moves when its own OSM features move). Signals, confidence 6/10.

    vibe = food/drink/nightlife POI density   per km²   anchor VIBE_FULL
    bike = cycleway length density            km/km²    anchor BIKE_FULL
    run  = park-area coverage (0–1) + off-street path-length density, blended

Each metric is computed independently and wrapped in try/except so one Overpass
failure (timeout / empty) leaves the others intact; a CCA with no features scores
0, not null. Park *points* already drive walk.py; here we use OSM park *polygons*
for area coverage.

Run: `.venv/bin/python scripts/scoring/lifestyle.py`  (hits Overpass; slow).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import requests  # noqa: E402
import geopandas as gpd  # noqa: E402
from shapely.geometry import Point, LineString, Polygon, shape  # noqa: E402

from utils.supabase_admin import get_admin_client  # noqa: E402
from scoring import fetch_all  # noqa: E402

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "Chicago.Intel/1.0 (neighborhood affordability engine)"}
CHI_BBOX = "41.64,-87.94,42.02,-87.52"  # S,W,N,E — Chicago
M_CRS = 26971  # Illinois East (meters) for area/length

VIBE_FULL = 80.0   # food/drink POIs per km² for full vibe credit (~dense corridor)
BIKE_FULL = 3.0    # km of cycleway per km² for full bike credit
PATH_FULL = 5.0    # km of off-street path per km² for full path credit


def _overpass(body: str) -> dict:
    r = requests.post(OVERPASS_URL, data={"data": body}, headers=HEADERS, timeout=180)
    r.raise_for_status()
    return r.json()


def _nodes(elements) -> list[Point]:
    return [Point(e["lon"], e["lat"]) for e in elements
            if e["type"] == "node" and "lat" in e]


def _ways_geom(elements):
    """Build shapely geoms from Overpass `out geom` ways (lines or polygons)."""
    lines, polys = [], []
    for e in elements:
        if e["type"] != "way" or "geometry" not in e:
            continue
        pts = [(p["lon"], p["lat"]) for p in e["geometry"]]
        if len(pts) < 2:
            continue
        if pts[0] == pts[-1] and len(pts) >= 4:
            polys.append(Polygon(pts))
        else:
            lines.append(LineString(pts))
    return lines, polys


def _anchor(density: float, full: float) -> float:
    return round(max(0.0, min(10.0, density / full * 10.0)), 2)


def compute() -> dict:
    client = get_admin_client()
    ccas = fetch_all(client, "ccas", "id,name,geometry", {"geometry": "not.is.null"})
    cca_m = gpd.GeoDataFrame(
        [{"id": c["id"], "name": c["name"]} for c in ccas],
        geometry=[shape(c["geometry"]) for c in ccas], crs=4326).to_crs(M_CRS)
    cca_m["area_km2"] = cca_m.geometry.area / 1e6

    scores: dict[int, dict] = {c["id"]: {} for c in ccas}

    # ---- vibe: POI density ----
    try:
        el = _overpass(
            f'[out:json][timeout:120];'
            f'node["amenity"~"^(restaurant|cafe|bar|pub|fast_food|nightclub|food_court|biergarten|ice_cream)$"]({CHI_BBOX});'
            f'out;')["elements"]
        pts = gpd.GeoDataFrame(geometry=_nodes(el), crs=4326).to_crs(M_CRS)
        j = gpd.sjoin(pts, cca_m[["geometry", "id"]], predicate="within", how="inner")
        cnt = j.groupby("id").size().to_dict()
        for r in cca_m.itertuples():
            if r.area_km2 > 0:
                scores[r.id]["vibe_score"] = _anchor(cnt.get(r.id, 0) / r.area_km2, VIBE_FULL)
    except Exception as e:  # noqa: BLE001
        print(f"vibe: SKIPPED ({e})")
    time.sleep(2)

    # ---- bike: cycleway length density ----
    try:
        el = _overpass(
            f'[out:json][timeout:120];'
            f'way["highway"="cycleway"]({CHI_BBOX});'
            f'out geom;')["elements"]
        lines, _ = _ways_geom(el)
        lg = gpd.GeoDataFrame(geometry=lines, crs=4326).to_crs(M_CRS)
        clipped = gpd.overlay(
            gpd.GeoDataFrame(geometry=lg.geometry).assign(g=1),
            cca_m[["geometry", "id"]], how="identity", keep_geom_type=False) \
            if not lg.empty else None
        if clipped is not None:
            clipped["km"] = clipped.geometry.length / 1000.0
            kml = clipped.dropna(subset=["id"]).groupby("id")["km"].sum().to_dict()
            for r in cca_m.itertuples():
                if r.area_km2 > 0:
                    scores[r.id]["bike_score"] = _anchor(kml.get(r.id, 0.0) / r.area_km2, BIKE_FULL)
    except Exception as e:  # noqa: BLE001
        print(f"bike: SKIPPED ({e})")
    time.sleep(2)

    # ---- run: park-area coverage + off-street path density ----
    try:
        el = _overpass(
            f'[out:json][timeout:150];'
            f'(way["leisure"="park"]({CHI_BBOX});'
            f' way["highway"~"^(path|footway)$"]({CHI_BBOX}););'
            f'out geom;')["elements"]
        lines, polys = _ways_geom(el)
        park_g = gpd.GeoDataFrame(geometry=polys, crs=4326).to_crs(M_CRS) if polys else None
        path_g = gpd.GeoDataFrame(geometry=lines, crs=4326).to_crs(M_CRS) if lines else None

        park_area = {}
        if park_g is not None and not park_g.empty:
            ov = gpd.overlay(cca_m[["geometry", "id"]], park_g[["geometry"]],
                             how="intersection", keep_geom_type=False)
            ov["a"] = ov.geometry.area / 1e6
            park_area = ov.groupby("id")["a"].sum().to_dict()

        path_km = {}
        if path_g is not None and not path_g.empty:
            ov = gpd.overlay(gpd.GeoDataFrame(geometry=path_g.geometry),
                             cca_m[["geometry", "id"]], how="identity", keep_geom_type=False)
            ov["km"] = ov.geometry.length / 1000.0
            path_km = ov.dropna(subset=["id"]).groupby("id")["km"].sum().to_dict()

        for r in cca_m.itertuples():
            if r.area_km2 <= 0:
                continue
            green = min(park_area.get(r.id, 0.0) / r.area_km2, 1.0)          # 0–1 coverage
            paths = min(path_km.get(r.id, 0.0) / r.area_km2 / PATH_FULL, 1.0)  # 0–1
            scores[r.id]["run_score"] = round(max(0.0, min(10.0, green * 6.0 + paths * 4.0)), 2)
    except Exception as e:  # noqa: BLE001
        print(f"run: SKIPPED ({e})")

    name = {c["id"]: c["name"] for c in ccas}
    payload = [{"id": cid, "name": name[cid], **s} for cid, s in scores.items() if s]
    for i in range(0, len(payload), 400):
        client.table("ccas").upsert(payload[i:i + 400]).execute()

    return {"ccas_scored": len(payload),
            "metrics": {k: sum(1 for s in scores.values() if k in s)
                        for k in ("vibe_score", "bike_score", "run_score")}}


if __name__ == "__main__":
    s = compute()
    print(f"lifestyle: ccas={s['ccas_scored']} metrics={s['metrics']}")

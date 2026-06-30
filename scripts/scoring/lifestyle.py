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


def _osm_layers():
    """Fetch the 3 OSM datasets ONCE city-wide → projected GeoDataFrames, reused
    for every grain (so adding tracts costs NO extra Overpass calls). Each layer
    is None if its query fails, so one failure doesn't kill the others."""
    vibe_pts = bike_lines = park_polys = path_lines = None
    try:
        el = _overpass(
            f'[out:json][timeout:120];'
            f'node["amenity"~"^(restaurant|cafe|bar|pub|fast_food|nightclub|food_court|biergarten|ice_cream)$"]({CHI_BBOX});'
            f'out;')["elements"]
        vibe_pts = gpd.GeoDataFrame(geometry=_nodes(el), crs=4326).to_crs(M_CRS)
    except Exception as e:  # noqa: BLE001
        print(f"vibe osm: SKIPPED ({e})")
    time.sleep(2)
    try:
        el = _overpass(
            f'[out:json][timeout:120];'
            f'way["highway"="cycleway"]({CHI_BBOX});'
            f'out geom;')["elements"]
        lines, _ = _ways_geom(el)
        bike_lines = gpd.GeoDataFrame(geometry=lines, crs=4326).to_crs(M_CRS) if lines else None
    except Exception as e:  # noqa: BLE001
        print(f"bike osm: SKIPPED ({e})")
    time.sleep(2)
    try:
        el = _overpass(
            f'[out:json][timeout:150];'
            f'(way["leisure"="park"]({CHI_BBOX});'
            f' way["highway"~"^(path|footway)$"]({CHI_BBOX}););'
            f'out geom;')["elements"]
        lines, polys = _ways_geom(el)
        park_polys = gpd.GeoDataFrame(geometry=polys, crs=4326).to_crs(M_CRS) if polys else None
        path_lines = gpd.GeoDataFrame(geometry=lines, crs=4326).to_crs(M_CRS) if lines else None
    except Exception as e:  # noqa: BLE001
        print(f"run osm: SKIPPED ({e})")
    return vibe_pts, bike_lines, park_polys, path_lines


def _score_polys(poly_m, osm) -> dict:
    """vibe/bike/run for each polygon in `poly_m` (needs id + area_km2 cols) from
    the prefetched OSM layers. Same formulas/anchors as before, grain-agnostic."""
    vibe_pts, bike_lines, park_polys, path_lines = osm
    scores: dict = {pid: {} for pid in poly_m["id"]}

    if vibe_pts is not None and not vibe_pts.empty:
        j = gpd.sjoin(vibe_pts, poly_m[["geometry", "id"]], predicate="within", how="inner")
        cnt = j.groupby("id").size().to_dict()
        for r in poly_m.itertuples():
            if r.area_km2 > 0:
                scores[r.id]["vibe_score"] = _anchor(cnt.get(r.id, 0) / r.area_km2, VIBE_FULL)

    if bike_lines is not None and not bike_lines.empty:
        clipped = gpd.overlay(gpd.GeoDataFrame(geometry=bike_lines.geometry).assign(g=1),
                              poly_m[["geometry", "id"]], how="identity", keep_geom_type=False)
        clipped["km"] = clipped.geometry.length / 1000.0
        kml = clipped.dropna(subset=["id"]).groupby("id")["km"].sum().to_dict()
        for r in poly_m.itertuples():
            if r.area_km2 > 0:
                scores[r.id]["bike_score"] = _anchor(kml.get(r.id, 0.0) / r.area_km2, BIKE_FULL)

    if park_polys is not None or path_lines is not None:
        park_area, path_km = {}, {}
        if park_polys is not None and not park_polys.empty:
            ov = gpd.overlay(poly_m[["geometry", "id"]], park_polys[["geometry"]],
                             how="intersection", keep_geom_type=False)
            ov["a"] = ov.geometry.area / 1e6
            park_area = ov.groupby("id")["a"].sum().to_dict()
        if path_lines is not None and not path_lines.empty:
            ov = gpd.overlay(gpd.GeoDataFrame(geometry=path_lines.geometry),
                             poly_m[["geometry", "id"]], how="identity", keep_geom_type=False)
            ov["km"] = ov.geometry.length / 1000.0
            path_km = ov.dropna(subset=["id"]).groupby("id")["km"].sum().to_dict()
        for r in poly_m.itertuples():
            if r.area_km2 <= 0:
                continue
            green = min(park_area.get(r.id, 0.0) / r.area_km2, 1.0)
            paths = min(path_km.get(r.id, 0.0) / r.area_km2 / PATH_FULL, 1.0)
            scores[r.id]["run_score"] = round(max(0.0, min(10.0, green * 6.0 + paths * 4.0)), 2)

    return scores


def _grain_gdf(client, table: str):
    """Projected polygon GeoDataFrame (id + area_km2) + id→name map for a grain."""
    named = table == "ccas"
    rows = fetch_all(client, table, ("id,name,geometry" if named else "id,geometry"),
                     {"geometry": "not.is.null"}, key=None if named else "id")
    gdf = gpd.GeoDataFrame([{"id": r["id"]} for r in rows],
                           geometry=[shape(r["geometry"]) for r in rows], crs=4326).to_crs(M_CRS)
    gdf["area_km2"] = gdf.geometry.area / 1e6
    names = {r["id"]: r["name"] for r in rows} if named else {}
    return gdf, names


def compute() -> dict:
    client = get_admin_client()
    osm = _osm_layers()
    out = {}
    for table in ("ccas", "tracts"):
        gdf, names = _grain_gdf(client, table)
        scores = _score_polys(gdf, osm)
        payload = []
        for pid, s in scores.items():
            if not s:
                continue
            row = {"id": pid, **s}
            if table == "ccas":
                row["name"] = names[pid]  # ccas.name is NOT NULL
            payload.append(row)
        for i in range(0, len(payload), 400):
            client.table(table).upsert(payload[i:i + 400]).execute()
        out[table] = {"scored": len(payload),
                      "metrics": {k: sum(1 for s in scores.values() if k in s)
                                  for k in ("vibe_score", "bike_score", "run_score")}}
    return out


if __name__ == "__main__":
    s = compute()
    print(f"lifestyle: ccas={s['ccas']} tracts={s['tracts']}")

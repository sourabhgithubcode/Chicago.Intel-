"""Chicago street centerlines — bronze GeoJSON features → silver rows.

Source: gisapps.cityofchicago.org/.../ExternalApps/Centerline/MapServer/0
Confidence: 9/10 — official city centerline data.

Silver schema (from supabase/migrations/007_create_streets.sql):
    streets(id TEXT PK, name TEXT, name_norm TEXT,
            from_addr INT, to_addr INT,
            cca_id INT, tract_id TEXT,
            geometry GEOMETRY(MULTILINESTRING, 4326))

`cca_id` and `tract_id` are populated by reconcile (`assign_streets_to_polygons()`),
not by this transformer.

Source field reference (ArcGIS MapServer/0 properties, UPPERCASE):
  STREET_NAME, PRE_DIR, SUF_DIR, STREET_TYPE       — name parts
  L_F_ADD, L_T_ADD, R_F_ADD, R_T_ADD               — address range (left/right)
  STATUS                                           — N=Normal (open), P=Private,
                                                     C=Constructed, UC=Under
                                                     Construction, V=Vacated,
                                                     UR=Unbuilt right-of-way
  OBJECTID                                         — stable per-row id
  GeoJSON geometry: LineString or MultiLineString
"""
from __future__ import annotations

from typing import Iterable, Optional

from shapely.geometry import shape
from shapely.geometry.linestring import LineString
from shapely.geometry.multilinestring import MultiLineString

# Chicago bounding box — drops segments outside the city.
CHI_NORTH, CHI_SOUTH = 42.023, 41.644
CHI_EAST, CHI_WEST = -87.524, -87.940

# Suffix abbreviation map used for both display name and `name_norm`.
# Mirrors the rules in lib/utils/normalizeAddress.js (DATA_DICTIONARY §4).
_SUFFIX_ABBR = {
    "STREET": "ST",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "DRIVE": "DR",
    "PLACE": "PL",
    "COURT": "CT",
    "PARKWAY": "PKWY",
    "ROAD": "RD",
    "LANE": "LN",
    "TERRACE": "TER",
    "HIGHWAY": "HWY",
}

# "N" = Normal/operating (~55.5K of 56.4K). Drop UC/V/UR/C (under construction,
# vacated, unbuilt right-of-way, "C"). Keep P (private but real, e.g. gated
# driveways and named private ways) — only 657 segments and they show up on
# real addresses.
_OPEN_STATUSES = {"N", "P"}


def _abbr_suffix(s: str) -> str:
    """Normalize a street suffix and return title case (e.g. 'AVENUE' → 'Ave')."""
    if not s:
        return ""
    upper = s.strip().upper()
    abbr = _SUFFIX_ABBR.get(upper, upper)
    return abbr.title()


def _build_name(p: dict) -> str:
    """Combine PRE_DIR + STREET_NAME + STREET_TYPE + SUF_DIR into a display name."""
    parts: list[str] = []
    pre = (p.get("PRE_DIR") or "").strip().upper()
    if pre:
        parts.append(pre)
    nam = (p.get("STREET_NAME") or "").strip()
    if nam:
        parts.append(nam.title())
    typ = _abbr_suffix(p.get("STREET_TYPE") or "")
    if typ:
        parts.append(typ)
    suf = (p.get("SUF_DIR") or "").strip().upper()
    if suf:
        parts.append(suf)
    return " ".join(parts)


def _normalize_name(name: str) -> str:
    """Normalize for joins: lowercase, collapse whitespace."""
    return " ".join(name.lower().split())


def _to_int(v) -> Optional[int]:
    """Cast to int, tolerating None and non-numeric values."""
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _addr_range(p: dict) -> tuple[Optional[int], Optional[int]]:
    """from_addr = min(L_F_ADD, R_F_ADD); to_addr = max(L_T_ADD, R_T_ADD)."""
    lf = _to_int(p.get("L_F_ADD"))
    rf = _to_int(p.get("R_F_ADD"))
    lt = _to_int(p.get("L_T_ADD"))
    rt = _to_int(p.get("R_T_ADD"))
    fr = [v for v in (lf, rf) if v is not None]
    to = [v for v in (lt, rt) if v is not None]
    return (min(fr) if fr else None, max(to) if to else None)


def _stable_id(feat: dict, props: dict) -> Optional[str]:
    """Prefer the feature's top-level `id` (=OBJECTID); fall back to props."""
    for v in (feat.get("id"), props.get("OBJECTID"), props.get("TRANS_ID")):
        if v not in (None, ""):
            return str(v)
    return None


def _in_chicago(geom) -> bool:
    """True if any vertex of the (multi)linestring is inside the Chicago bbox."""
    if isinstance(geom, LineString):
        coords_iter = [geom.coords]
    elif isinstance(geom, MultiLineString):
        coords_iter = [g.coords for g in geom.geoms]
    else:
        return False
    for coords in coords_iter:
        for x, y in coords:
            if CHI_WEST <= x <= CHI_EAST and CHI_SOUTH <= y <= CHI_NORTH:
                return True
    return False


def to_silver(features: Iterable[dict]) -> list[dict]:
    """Map raw ArcGIS GeoJSON street centerline features to streets silver rows."""
    silver: list[dict] = []
    seen: set[str] = set()

    for feat in features:
        props = feat.get("properties") or {}

        status = props.get("STATUS")
        if status is not None:
            s = str(status).strip().upper()
            # blank/whitespace status is observed in the source — treat as
            # unknown and drop. Only accept the documented "open" codes.
            if s not in _OPEN_STATUSES:
                continue

        sid = _stable_id(feat, props)
        if not sid or sid in seen:
            continue

        geom_json = feat.get("geometry")
        if not geom_json:
            continue
        try:
            geom = shape(geom_json)
        except Exception:
            continue
        if isinstance(geom, LineString):
            geom = MultiLineString([geom])
        if not isinstance(geom, MultiLineString) or geom.is_empty:
            continue
        if not _in_chicago(geom):
            continue

        name = _build_name(props)
        if not name:
            continue

        from_addr, to_addr = _addr_range(props)

        seen.add(sid)
        silver.append({
            "id": sid,
            "name": name,
            "name_norm": _normalize_name(name),
            "from_addr": from_addr,
            "to_addr": to_addr,
            "geometry": f"SRID=4326;{geom.wkt}",
            # cca_id / tract_id populated by reconcile, not here
        })

    return silver

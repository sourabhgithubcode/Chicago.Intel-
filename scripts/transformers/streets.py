"""Chicago street centerlines — bronze rows → silver rows for streets table.

Source: Chicago Data Portal Socrata 6imu-meau (free, no key required).
Confidence: 9/10 — official city centerline data.

Silver schema (from supabase/migrations/007_create_streets.sql):
    streets(id TEXT PK, name TEXT, name_norm TEXT,
            from_addr INT, to_addr INT,
            cca_id INT, tract_id TEXT,
            geometry GEOMETRY(MULTILINESTRING, 4326))

`cca_id` and `tract_id` are populated by reconcile (`assign_streets_to_polygons()`),
not by this transformer.

Field reference for 6imu-meau (verified against the public dataset schema):
  street_nam, pre_dir, suf_dir, street_typ — name parts
  l_f_add, l_t_add, r_f_add, r_t_add        — address range (left/right side)
  the_geom                                  — GeoJSON LineString or MultiLineString
  status                                    — "OPEN" / closed / proposed
"""

from typing import Iterable, Optional

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


def _abbr_suffix(s: str) -> str:
    """Normalize a street suffix and return title case (e.g. 'AVENUE' → 'Ave').

    Display convention is title case ('N Lincoln Ave'), not the all-caps form
    used on signage. The abbreviation map keys stay uppercase because that's
    how Socrata emits the source.
    """
    if not s:
        return ""
    upper = s.strip().upper()
    abbr = _SUFFIX_ABBR.get(upper, upper)
    # Title-case the result so 'AVE' → 'Ave', 'ST' → 'St'.
    return abbr.title()


def _build_name(r: dict) -> str:
    """Combine pre_dir + street_nam + street_typ + suf_dir into a display name."""
    parts: list[str] = []
    pre = (r.get("pre_dir") or "").strip().upper()
    if pre:
        parts.append(pre)
    nam = (r.get("street_nam") or "").strip()
    if nam:
        parts.append(nam.title())
    typ = _abbr_suffix(r.get("street_typ") or "")
    if typ:
        parts.append(typ)
    suf = (r.get("suf_dir") or "").strip().upper()
    if suf:
        parts.append(suf)
    return " ".join(parts)


def _normalize_name(name: str) -> str:
    """Normalize for joins: lowercase, collapse whitespace."""
    return " ".join(name.lower().split())


def _to_int(v) -> Optional[int]:
    """Cast to int, tolerating None and non-numeric strings."""
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _addr_range(r: dict) -> tuple[Optional[int], Optional[int]]:
    """from_addr = min(l_f_add, r_f_add); to_addr = max(l_t_add, r_t_add)."""
    lf = _to_int(r.get("l_f_add"))
    rf = _to_int(r.get("r_f_add"))
    lt = _to_int(r.get("l_t_add"))
    rt = _to_int(r.get("r_t_add"))

    fr = [v for v in (lf, rf) if v is not None]
    to = [v for v in (lt, rt) if v is not None]
    return (min(fr) if fr else None, max(to) if to else None)


def _vertex_in_chicago(vertex: list) -> bool:
    if not vertex or len(vertex) < 2:
        return False
    lng, lat = vertex[0], vertex[1]
    return CHI_SOUTH <= lat <= CHI_NORTH and CHI_WEST <= lng <= CHI_EAST


def _part_in_chicago(part: list) -> bool:
    """A segment counts as in-Chicago if at least one vertex is inside the bbox."""
    return any(_vertex_in_chicago(v) for v in part)


def _format_part(part: list) -> str:
    """Format a list of [lng, lat] vertices as PostGIS LINESTRING text."""
    return "(" + ", ".join(f"{v[0]} {v[1]}" for v in part) + ")"


def _to_wkt(geom: dict) -> Optional[str]:
    """Convert Socrata GeoJSON to PostGIS MULTILINESTRING WKT.

    Socrata returns LineString or MultiLineString. A LineString is wrapped
    into a single-part MultiLineString to match the schema.
    """
    if not isinstance(geom, dict):
        return None
    geom_type = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return None

    if geom_type == "LineString":
        if not _part_in_chicago(coords):
            return None
        return f"SRID=4326;MULTILINESTRING({_format_part(coords)})"

    if geom_type == "MultiLineString":
        valid = [p for p in coords if _part_in_chicago(p)]
        if not valid:
            return None
        parts = ", ".join(_format_part(p) for p in valid)
        return f"SRID=4326;MULTILINESTRING({parts})"

    return None


def _stable_id(r: dict) -> Optional[str]:
    """Prefer the dataset's own street_id; fall back to Socrata row id (`:id`)."""
    for key in ("street_id", "objectid", ":id"):
        v = r.get(key)
        if v not in (None, ""):
            return str(v)
    return None


def to_silver(raw_rows: Iterable[dict]) -> list[dict]:
    """Map raw Socrata street centerline rows to streets silver rows."""
    silver: list[dict] = []
    seen: set[str] = set()

    for r in raw_rows:
        # Filter to OPEN streets when status field is present.
        # If status missing, accept the row (some snapshots omit the column).
        status = r.get("status")
        if status:
            s = str(status).strip().upper()
            if s and s != "OPEN":
                continue

        sid = _stable_id(r)
        if not sid or sid in seen:
            continue

        wkt = _to_wkt(r.get("the_geom"))
        if not wkt:
            continue

        name = _build_name(r)
        if not name:
            continue

        from_addr, to_addr = _addr_range(r)

        seen.add(sid)
        silver.append({
            "id": sid,
            "name": name,
            "name_norm": _normalize_name(name),
            "from_addr": from_addr,
            "to_addr": to_addr,
            "geometry": wkt,
            # cca_id / tract_id populated by reconcile, not here
        })

    return silver

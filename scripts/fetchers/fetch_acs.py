"""US Census Bureau ACS 5-year (Tier 3 pipeline, free).

Source: api.census.gov/data/{vintage}/acs/acs5
Confidence: 8/10 at CCA, 6/10 at tract (§13.3, §13.22).
Env: CENSUS_API_KEY. Rate limit: 500 queries/day per key.

Variables (§13.22):
  B25064_001E/M  median gross rent + MOE
  B19013_001E/M  median household income + MOE
  B25002_002E/_003E  occupied / vacant — drives vacancy_rate
  B25003_001E/_002E/_003E  total / owner-occupied / renter-occupied — drives tenure
  B01003_001E    total population (drives pop-weighting in §5)
"""

import os
from typing import Iterable, Optional

import requests

API_KEY = os.getenv("CENSUS_API_KEY")
BASE = "https://api.census.gov/data/2023/acs/acs5"
SENTINELS = {-666666666, -999999999, -888888888}

# Pulled in one batch — Census API returns rows of strings; first row is header.
VARS = [
    "B25064_001E", "B25064_001M",          # rent
    "B19013_001E", "B19013_001M",          # income
    "B25002_002E", "B25002_003E",          # vacancy
    "B25003_001E", "B25003_002E", "B25003_003E",  # tenure
    "B01003_001E",                          # population
]


def _to_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return None if n in SENTINELS else n


def _ratio(num: Optional[int], denom: Optional[int]) -> Optional[float]:
    if num is None or denom is None or denom <= 0:
        return None
    r = num / denom
    return max(0.0, min(1.0, round(r, 3)))


def fetch_all(state_fips: str = "17", county_fips: str = "031") -> list[list]:
    """One Census API call returning all variables for all Cook County tracts."""
    if not API_KEY:
        raise RuntimeError("CENSUS_API_KEY is not set")
    params = {
        "get": ",".join(VARS),
        "for": "tract:*",
        "in": f"state:{state_fips} county:{county_fips}",
        "key": API_KEY,
    }
    res = requests.get(BASE, params=params, timeout=30)
    res.raise_for_status()
    return res.json()


def to_silver(raw: Iterable[list]) -> list[dict]:
    """Census returns header row + data rows. Map to tracts silver rows."""
    rows = list(raw)
    if not rows:
        return []
    header = rows[0]
    idx = {col: i for i, col in enumerate(header)}

    silver: list[dict] = []
    for r in rows[1:]:
        get = lambda k: r[idx[k]] if k in idx else None
        geoid = f"{get('state')}{get('county')}{get('tract')}"

        occupied = _to_int(get("B25002_002E"))
        vacant = _to_int(get("B25002_003E"))
        total_units = (occupied or 0) + (vacant or 0) if (occupied is not None or vacant is not None) else None

        owner = _to_int(get("B25003_002E"))
        renter = _to_int(get("B25003_003E"))
        tenure_total = _to_int(get("B25003_001E"))

        silver.append({
            "id": geoid,
            "rent_median":         _to_int(get("B25064_001E")),
            "rent_moe":            _to_int(get("B25064_001M")),
            "income_median":       _to_int(get("B19013_001E")),
            "income_moe":          _to_int(get("B19013_001M")),
            "vacancy_rate":        _ratio(vacant, total_units),
            "owner_occupied_pct":  _ratio(owner, tenure_total),
            "renter_occupied_pct": _ratio(renter, tenure_total),
            "population":          _to_int(get("B01003_001E")),
        })
    return silver


def run(run_id: str) -> list[dict]:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from utils.bronze_store import write_bronze

    raw = fetch_all()
    write_bronze("acs", run_id, [{"row": r} for r in raw])
    return to_silver(raw)


if __name__ == "__main__":
    raw = fetch_all()
    print(f"acs: fetched {len(raw) - 1} tract rows × {len(VARS)} variables")

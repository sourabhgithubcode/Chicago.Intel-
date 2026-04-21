"""API #6 — US Census Bureau (Tier 3 pipeline, free).

Tables: B25064 (rent), B19013 (income), B01003 (population), B25003 (tenure).
Env: CENSUS_API_KEY. Rate limit: 500 queries/day per key.
Writes to data/processed/acs_*.csv for the loader to upsert.
"""

import os

import requests

API_KEY = os.getenv("CENSUS_API_KEY")
BASE = "https://api.census.gov/data/2023/acs/acs5"


def fetch_rent_by_tract(state_fips: str = "17", county_fips: str = "031") -> list:
    """Pull median contract rent (B25064_001E) for all Cook County tracts."""
    if not API_KEY:
        raise RuntimeError("CENSUS_API_KEY is not set")
    # TODO: paginate, write to data/processed/acs_rent_tracts.csv, add MOE column.
    params = {
        "get": "B25064_001E,NAME",
        "for": "tract:*",
        "in": f"state:{state_fips} county:{county_fips}",
        "key": API_KEY,
    }
    res = requests.get(BASE, params=params, timeout=30)
    res.raise_for_status()
    return res.json()


if __name__ == "__main__":
    print(f"acs: fetched {len(fetch_rent_by_tract()) - 1} tract rows")

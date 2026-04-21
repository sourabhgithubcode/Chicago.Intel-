"""API #7 — Chicago Data Portal / Parks (Tier 3 pipeline).

Dataset: ej32-qgdr (Park District facilities). Env: CHICAGO_DATA_TOKEN.
"""

import os

from sodapy import Socrata

DOMAIN = "data.cityofchicago.org"
DATASET = "ej32-qgdr"
TOKEN = os.getenv("CHICAGO_DATA_TOKEN")


def fetch_parks(limit: int = 10_000) -> list:
    client = Socrata(DOMAIN, TOKEN)
    return client.get(DATASET, limit=limit)


if __name__ == "__main__":
    print(f"parks: fetched {len(fetch_parks())} rows")

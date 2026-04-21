"""API #7 — Chicago Data Portal / 311 (Tier 3 pipeline).

Dataset: kn9c-c2s2 (311 service requests). Env: CHICAGO_DATA_TOKEN.
Pulls: building violations, heat complaints, bed bug reports.
"""

import os

from sodapy import Socrata

DOMAIN = "data.cityofchicago.org"
DATASET = "kn9c-c2s2"
TOKEN = os.getenv("CHICAGO_DATA_TOKEN")

RELEVANT_TYPES = (
    "Building Violation",
    "No Heat Complaint",
    "Bed Bug Complaint",
    "Rodent Baiting/Rat Complaint",
)


def fetch_recent(limit: int = 100_000) -> list:
    client = Socrata(DOMAIN, TOKEN)
    where = " OR ".join(f"sr_type='{t}'" for t in RELEVANT_TYPES)
    return client.get(DATASET, where=where, limit=limit)


if __name__ == "__main__":
    print(f"311: fetched {len(fetch_recent())} rows")
